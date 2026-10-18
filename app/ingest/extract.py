"""Deterministic text cleaning/classification; no LLM or external language service."""
import re
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException
from pypdf import PdfReader
from .types import Fetched, IngestError, Parsed, Section

PARSER_VERSION = 't06-v4'
DetectorFactory.seed = 0
LANGUAGES = {'de', 'en', 'fr', 'it'}


def clean(value: str) -> str:
    return ' '.join(value.replace('\x00', '').split())


def language(text: str, hint: str | None = None) -> str | None:
    hinted = (hint or '').lower().split('-')[0]
    if hinted in LANGUAGES:
        return hinted
    try:
        result = detect_langs(text)
        if result and result[0].lang in LANGUAGES and result[0].prob >= .8:
            return result[0].lang
    except LangDetectException:
        pass
    return None


def classify(url: str, title: str, headings: list[str]) -> str:
    path = urlsplit(url).path.lower()
    title = title.lower()
    if (path.rstrip('/') in ('/en/projects', '/de/projekte', '/research', '/forschung')
            or '/research_programs/' in path
            or re.fullmatch(r'/(research|forschung)/index_(eng|ger|fra|ita)\.html', path)):
        return 'directory'
    if re.search(r'/(people|persons|personen|staff|members|group_members|research_groups|forschungsgruppen)/(index_(eng|ger|fra|ita)\.html)?$', path):
        return 'directory'
    if re.search(r'/(persons?|people|personen|staff|members)/[^/]+', path):
        return 'person'
    if re.search(r'/(projects?|projekte)/[^/]+', path):
        return 'project'
    if any(t in title for t in ('core facilit', 'infrastructure', 'platform')):
        return 'infrastructure'
    if any(t in title for t in ('service', 'dienstleistung')):
        return 'service'
    if any(t in title for t in ('group', 'laboratory', 'institute', 'institut', 'centre', 'center', 'department')):
        return 'unit'
    if re.search(r'/research/(?!research_|media_|index_)[a-z0-9_-]+/index_', path):
        return 'unit'
    if len(headings) > 3 or any(t in title for t in ('research', 'forschung', 'projects', 'projekte')):
        return 'directory'
    return 'other'


def _source_date(soup, modified=False) -> str | None:
    options = ({'property': 'article:modified_time'}, {'itemprop': 'dateModified'}) if modified else ({'property': 'article:published_time'}, {'name': 'date'}, {'itemprop': 'datePublished'})
    for attrs in options:
        node = soup.find('meta', attrs=attrs)
        if node and node.get('content'):
            value = node['content']
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
                return value
            except ValueError:
                pass
    return None


def parse_html(page: Fetched) -> Parsed:
    soup = BeautifulSoup(page.body, 'html.parser')
    hint = soup.html.get('lang') if soup.html else None
    content_date = _source_date(soup)
    last_modified = _source_date(soup, modified=True)
    links = list(dict.fromkeys(urljoin(page.url, a['href']) for a in soup.find_all('a', href=True)))
    variants = []
    for a in soup.find_all(['a', 'link'], href=True):
        if a.get('hreflang') and a['hreflang'].split('-')[0] in LANGUAGES:
            variants.append(urljoin(page.url, a['href']))
    # UniBE uses language selectors with linked EN/DE labels, not always hreflang.
    for box in soup.select('#language, .language, .languages, [id*=sprach], [class*=language]'):
        variants += [urljoin(page.url, a['href']) for a in box.find_all('a', href=True)]
    for a in soup.find_all('a', href=True):
        if clean(a.get_text(' ', strip=True)).lower() in ('en', 'de', 'fr', 'it', 'english', 'german', 'deutsch', 'français', 'italiano'):
            variants.append(urljoin(page.url, a['href']))
    raw_title = clean(soup.title.get_text(' ', strip=True)) if soup.title else ''
    for node in soup.select('script, style, noscript, nav, header, footer, form, aside, '
                            '[role=navigation], .breadcrumb, .breadcrumbs, .cookie-banner, .et_pb_social_media_follow, .et_pb_newsletter'):
        node.decompose()
    main = soup.select_one('main, [role=main], #main-content, #content, #main') or soup.body or soup
    if re.search(r'/(project|projekte)/[^/]+', urlsplit(page.url).path):
        # WordPress/Divi can nest related project cards inside the main article.
        article = next((a for a in main.find_all('article') if a.find('h1')), None)
        if article is not None:
            main = article
            for related in list(main.find_all('article')):
                related.decompose()
            for widget in list(main.select('.et_pb_blog_grid, .et_pb_blog_0')):
                widget.decompose()
    h1 = main.find('h1')
    title = clean(h1.get_text(' ', strip=True)) if h1 else raw_title
    if title.lower() in ('research', 'forschung', 'projects', 'projekte'):
        title = raw_title or title
    sections = []
    heading, chunks = title, []
    for node in main.find_all(['h1', 'h2', 'h3', 'p', 'li', 'table']):
        if node.find_parent(['p', 'li', 'table']) is not None:
            continue
        value = clean(node.get_text(' ', strip=True))
        if not value:
            continue
        if node.name.startswith('h'):
            if any(term in value.lower() for term in ('newsletter', 'sign up for our')):
                break
            if value.lower() in ('labs', 'program contact', 'contact', 'kontakt', 'scientific overview'):
                chunks.append(value)
                continue
            if chunks:
                sections.append(Section(heading=heading, text='\n'.join(chunks)))
            heading, chunks = value, [value]
        else:
            chunks.append(value)
    if chunks:
        sections.append(Section(heading=heading, text='\n'.join(chunks)))
    if not sections:
        value = clean(main.get_text(' ', strip=True))
        if value:
            sections = [Section(heading=title, text=value)]
    text = '\n\n'.join(s.text for s in sections)
    if len(text) < 40:
        code = 'js_rendered_candidate' if soup.find(id=re.compile(r'^(app|root|__next)$')) else 'no_usable_text'
        raise IngestError(code)
    return Parsed(title=title or 'Untitled', sections=sections, language=language(text, hint),
                  page_type=classify(page.url, title, [s.heading for s in sections]),
                  links=links, variants=list(dict.fromkeys(variants)), content_date=content_date, last_modified=last_modified)


def parse_pdf(page: Fetched) -> Parsed:
    try:
        pdf = PdfReader(BytesIO(page.body))
        if pdf.is_encrypted:
            raise IngestError('encrypted_pdf')
        sections = [Section(heading=f'Page {i}', text=clean(p.extract_text() or ''), page_number=i)
                    for i, p in enumerate(pdf.pages, 1)]
    except IngestError:
        raise
    except Exception:
        raise IngestError('invalid_pdf') from None
    sections = [s for s in sections if s.text]
    if not sections:
        raise IngestError('scanned_or_empty_pdf')
    text = '\f'.join(s.text for s in sections)
    title = str((pdf.metadata or {}).get('/Title') or urlsplit(page.url).path.rstrip('/').rsplit('/', 1)[-1] or urlsplit(page.url).hostname)
    return Parsed(title=title, sections=sections, language=language(text), page_type='other')


def parse(page: Fetched) -> Parsed:
    if page.media_type == 'application/pdf' or page.body.startswith(b'%PDF-'):
        return parse_pdf(page)
    if page.media_type in ('text/html', 'application/xhtml+xml'):
        return parse_html(page)
    raise IngestError('unsupported_media_type')


def split_sentences(text: str) -> list[str]:
    # Conservative punctuation/newline split. Preserve exact substrings of cleaned text;
    # abbreviation handling can evolve only with a new parser version.
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜÀÉÈÊÎÔÇ0-9])|\n+', text) if s.strip()]
