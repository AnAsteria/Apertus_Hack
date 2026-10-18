"""Bounded, scope-checked fetches. Source requests never originate from query routes."""
import ipaddress
import socket
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import httpx
from protego import Protego
from .types import Fetched, IngestError, Source

USER_AGENT = 'BernMatch/0.1 (public research source snapshot)'


def canonical_url(url: str) -> str:
    u = urlsplit(url)
    scheme, host = u.scheme.lower(), (u.hostname or '').lower()
    if scheme not in ('http', 'https') or not host or u.username or u.password:
        raise IngestError('invalid_url')
    try:
        port = u.port
    except ValueError:
        raise IngestError('invalid_url') from None
    if port not in (None, 80, 443):
        raise IngestError('unsupported_port')
    netloc = host if port in (None, 443 if scheme == 'https' else 80) else f'{host}:{port}'
    query = []
    for part in u.query.split('&') if u.query else []:
        for key, value in parse_qsl(part, keep_blank_values=True):
            if key.lower().startswith('utm_') or key.lower() in ('fbclid', 'gclid'):
                continue
            query.append((key, value, '=' in part))
    encoded = []
    for key, value, has_equal in sorted(query):
        item = urlencode([(key, value)])
        encoded.append(item if has_equal else item.removesuffix('='))
    return urlunsplit((scheme, netloc, u.path or '/', '&'.join(encoded), ''))


def fetch_url(url: str) -> str:
    # Check syntax/scheme/credentials, but preserve the original query for robots
    # and the actual HTTP request. Identity normalisation must never evade robots.
    canonical_url(url)
    u = urlsplit(url)
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path or '/', u.query, ''))


def in_scope(url: str, source: Source) -> bool:
    try:
        u = urlsplit(canonical_url(url))
    except IngestError:
        return False
    if u.hostname not in source.config.allowed_domains:
        return False
    return any(prefix == '/' or u.path == prefix.rstrip('/') or u.path.startswith(prefix.rstrip('/') + '/')
               for prefix in source.config.allowed_paths)


def public_addresses(host: str):
    try:
        addresses = [r[4][0] for r in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
    except OSError:
        raise IngestError('dns_failure') from None
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise IngestError('private_or_nonpublic_address')
    return addresses


class Fetcher:
    def __init__(self, client=None, resolver=public_addresses, sleep=time.sleep, clock=time.monotonic):
        self.client = client or httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False,
                                            trust_env=False, headers={'User-Agent': USER_AGENT})
        self.resolver, self.sleep, self.clock = resolver, sleep, clock
        self.last = {}
        self.robots = {}
        self.requests = 0
        self.retries = 0

    def close(self):
        self.client.close()

    def _request(self, url: str, source: Source):
        host = urlsplit(url).hostname
        self.resolver(host)
        for attempt in range(3):
            delay = self.last.get(host, -1e9) + 1 / source.config.requests_per_second - self.clock()
            if delay > 0:
                self.sleep(delay)
            try:
                self.requests += 1
                with self.client.stream('GET', url, headers={'User-Agent': USER_AGENT}) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > source.max_bytes:
                            raise IngestError('response_too_large')
                        chunks.append(chunk)
                    status, headers, body = response.status_code, dict(response.headers), b''.join(chunks)
            except httpx.TransportError:
                if attempt == 2:
                    raise IngestError('transport_failure') from None
                status, headers, body = 503, {}, b''
            finally:
                self.last[host] = self.clock()
            if status in (408, 429) or status >= 500:
                if attempt < 2:
                    self.retries += 1
                    # Retry-After is deliberately capped; no unbounded blocking jobs.
                    retry_after = headers.get('retry-after', '')
                    wait = min(10, float(retry_after)) if retry_after.isdigit() else 2 ** attempt
                    self.sleep(wait)
                    continue
            return status, headers, body
        raise IngestError('retry_limit')

    def _policy(self, url: str, source: Source):
        u = urlsplit(url)
        origin = f'{u.scheme}://{u.netloc}'
        if origin in self.robots:
            return self.robots[origin]
        robots_url = origin + '/robots.txt'
        # robots is a control document: path allowlists apply to content, not its location.
        for _ in range(6):
            if urlsplit(robots_url).hostname not in source.config.allowed_domains:
                raise IngestError('robots_redirect_outside_scope')
            status, headers, body = self._request(robots_url, source)
            if status in (301, 302, 303, 307, 308) and headers.get('location'):
                robots_url = canonical_url(urljoin(robots_url, headers['location']))
                continue
            if status in (404, 410):
                policy = None  # absence is distinct from a failed/denied robots request
            elif status == 200 and '<html' not in body[:500].decode('utf-8', errors='ignore').lower():
                policy = Protego.parse(body.decode('utf-8', errors='replace'))
            else:
                raise IngestError('robots_unavailable')
            self.robots[origin] = policy
            return policy
        raise IngestError('robots_redirect_limit')

    def fetch(self, url: str, source: Source) -> Fetched:
        requested = fetch_url(url)
        current, redirects = requested, []
        for _ in range(6):
            if not in_scope(current, source):
                raise IngestError('outside_scope')
            self.resolver(urlsplit(current).hostname)
            policy = self._policy(current, source)
            if policy is not None and not policy.can_fetch(current, USER_AGENT):
                raise IngestError('robots_disallowed')
            status, headers, body = self._request(current, source)
            if status in (301, 302, 303, 307, 308) and headers.get('location'):
                redirects.append(current)
                current = fetch_url(urljoin(current, headers['location']))
                continue
            if status != 200:
                raise IngestError('http_' + str(status))
            last_modified = None
            if headers.get('last-modified'):
                try:
                    last_modified = parsedate_to_datetime(headers['last-modified']).isoformat()
                except (TypeError, ValueError, OverflowError):
                    pass
            return Fetched(requested_url=requested, url=current, body=body,
                           media_type=headers.get('content-type', '').split(';')[0].lower(),
                           fetched_at=datetime.now(timezone.utc).isoformat(), last_modified=last_modified,
                           redirects=redirects)
        raise IngestError('redirect_limit')
