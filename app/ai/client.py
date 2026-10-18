"""Replaceable Apertus inference client (CONTRACTS section 6, T05).

Talks to any OpenAI-compatible chat endpoint: the CSCS/Keera gateway in
development, or a local server (llama.cpp) for the offline proof. Callers
must treat every failure as "enrichment unavailable": nothing in the keyword
search path may depend on this module.

Guarantees:
- The API key is sent only in the Authorization header; it is never logged,
  returned in errors or included in repr().
- Logs and metrics carry model, status, timing and token counts only, never
  prompts, company text or model output.
- Structured output tries backend JSON-schema constrained decoding first
  (`backend_constrained`). If the endpoint rejects it, we fall back to asking
  for JSON and validating it (`validated_retry_fallback`), which is a WEAKER
  guarantee. Neither mode proves semantic support of any claim.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, Literal

import httpx
from pydantic import BaseModel, ValidationError

from .config import InferenceConfig

log = logging.getLogger("bernmatch.inference")

DecodingMode = Literal["backend_constrained", "validated_retry_fallback"]
BACKEND_CONSTRAINED: DecodingMode = "backend_constrained"
VALIDATED_RETRY_FALLBACK: DecodingMode = "validated_retry_fallback"


class InferenceError(Exception):
    """`code` is one of DISABLED, AUTH, NOT_FOUND, BAD_REQUEST, RATE_LIMITED,
    TIMEOUT, UNAVAILABLE, BAD_OUTPUT. Messages are fixed text: never echo
    prompts, outputs or keys."""

    def __init__(self, code: str, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.retryable = retryable
        self.status = status


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens, self.completion_tokens + other.completion_tokens)


@dataclass
class ChatResult:
    text: str
    model: str
    usage: Usage
    latency_s: float
    attempts: int
    finish_reason: str | None = None
    tool_calls: list = field(default_factory=list)


@dataclass
class JsonResult:
    value: BaseModel
    decoding_mode: DecodingMode
    model: str
    usage: Usage
    latency_s: float
    attempts: int  # model calls made, including invalid outputs


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


class Meter:
    """Thread-safe per-model counters for the measurement tasks (T16/T20)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._m: dict[str, dict] = {}

    def _get(self, model: str) -> dict:
        return self._m.setdefault(model, {"calls": 0, "failures": 0, "retries": 0, "invalid_outputs": 0,
                                          "prompt_tokens": 0, "completion_tokens": 0,
                                          "latencies_s": [], "ttft_s": []})

    def record(self, model: str, *, usage: Usage | None = None, latency_s: float | None = None,
               ttft_s: float | None = None, failed: bool = False, retried: bool = False,
               invalid: bool = False) -> None:
        with self._lock:
            m = self._get(model)
            if usage is not None:
                m["calls"] += 1
                m["prompt_tokens"] += usage.prompt_tokens
                m["completion_tokens"] += usage.completion_tokens
            if latency_s is not None:
                m["latencies_s"].append(latency_s)
            if ttft_s is not None:
                m["ttft_s"].append(ttft_s)
            m["failures"] += failed
            m["retries"] += retried
            m["invalid_outputs"] += invalid

    def snapshot(self) -> dict:
        with self._lock:
            out = {}
            for model, m in self._m.items():
                lat, ttft = m["latencies_s"], m["ttft_s"]
                out[model] = {k: v for k, v in m.items() if k not in ("latencies_s", "ttft_s")} | {
                    "latency_median_s": _percentile(lat, 0.5), "latency_p95_s": _percentile(lat, 0.95),
                    "ttft_median_s": _percentile(ttft, 0.5), "samples": len(lat)}
            return out


def extract_json(text: str) -> str:
    """First JSON object in a reply; strips code fences and surrounding prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _status_error(r: httpx.Response) -> InferenceError:
    s = r.status_code
    if s in (401, 403):
        return InferenceError("AUTH", "Inference endpoint rejected the credentials.", status=s)
    if s == 404:
        return InferenceError("NOT_FOUND", "Model or route not available for this key.", status=s)
    if s == 408:
        return InferenceError("TIMEOUT", "Inference endpoint timed out.", True, status=s)
    if s == 429:
        return InferenceError("RATE_LIMITED", "Inference endpoint rate limit reached.", True, status=s)
    if s >= 500:
        return InferenceError("UNAVAILABLE", "Inference endpoint unavailable.", True, status=s)
    return InferenceError("BAD_REQUEST", "Inference endpoint rejected the request.", status=s)


class ApertusClient:
    def __init__(self, config: InferenceConfig | None = None, *, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.config = config or InferenceConfig.from_env()
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        self._http = httpx.Client(base_url=self.config.base_url, timeout=self.config.timeout_s,
                                  headers=headers, transport=transport)
        self._sem = threading.BoundedSemaphore(self.config.max_concurrency)
        self._sleep = sleep
        self.meter = Meter()
        # Learned on first structured call: True/False once the backend has answered.
        self.schema_support: bool | None = None

    def __repr__(self) -> str:
        return f"ApertusClient({self.config.redacted()})"

    def close(self) -> None:
        self._http.close()

    # --- transport ------------------------------------------------------------
    def _require_enabled(self) -> None:
        if not self.config.enabled:
            raise InferenceError("DISABLED", "Inference is not configured.")

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.config.backoff_max_s)
            except ValueError:
                pass
        base = self.config.backoff_base_s * (2 ** (attempt - 1))
        return min(base, self.config.backoff_max_s) * (0.5 + random.random() / 2)

    def _post(self, payload: dict) -> tuple[dict, int, float]:
        """POST /chat/completions with bounded retries. Returns (json, attempts, latency of the last try)."""
        self._require_enabled()
        model = payload["model"]
        attempt = 0
        while True:
            attempt += 1
            retry_after = None
            t0 = time.perf_counter()
            try:
                with self._sem:
                    r = self._http.post("/chat/completions", json=payload)
            except httpx.TimeoutException:
                err = InferenceError("TIMEOUT", "Inference request timed out.", True)
            except httpx.TransportError:
                err = InferenceError("UNAVAILABLE", "Inference endpoint unreachable.", True)
            else:
                latency = time.perf_counter() - t0
                if r.status_code < 400:
                    try:
                        return r.json(), attempt, latency
                    except ValueError:
                        err = InferenceError("UNAVAILABLE", "Inference endpoint returned non-JSON.", True)
                else:
                    err = _status_error(r)
                    retry_after = r.headers.get("retry-after")
            log.warning("inference error model=%s code=%s status=%s attempt=%d", model, err.code, err.status, attempt)
            if not err.retryable or attempt > self.config.max_retries:
                self.meter.record(model, failed=True)
                raise err
            self.meter.record(model, retried=True)
            self._sleep(self._backoff(attempt, retry_after))

    # --- public API -------------------------------------------------------------
    def chat(self, messages: list[dict], *, model: str | None = None, max_tokens: int = 512,
             temperature: float = 0.2, response_format: dict | None = None,
             tools: list[dict] | None = None) -> ChatResult:
        model = model or self.config.model
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        t0 = time.perf_counter()
        data, attempts, _ = self._post(payload)
        latency = time.perf_counter() - t0
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
        except (KeyError, IndexError, TypeError):
            self.meter.record(model, failed=True)
            raise InferenceError("UNAVAILABLE", "Inference response had no choices.")
        u = data.get("usage") or {}
        usage = Usage(u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0)
        self.meter.record(model, usage=usage, latency_s=latency)
        log.info("inference ok model=%s attempts=%d latency_s=%.3f prompt_tokens=%d completion_tokens=%d",
                 model, attempts, latency, usage.prompt_tokens, usage.completion_tokens)
        return ChatResult(text=msg.get("content") or "", model=model, usage=usage, latency_s=latency,
                          attempts=attempts, finish_reason=choice.get("finish_reason"),
                          tool_calls=msg.get("tool_calls") or [])

    def complete_json(self, messages: list[dict], schema: type[BaseModel], *, model: str | None = None,
                      max_tokens: int = 1024, temperature: float = 0.0,
                      max_attempts: int | None = None) -> JsonResult:
        """Return a validated `schema` instance or raise InferenceError("BAD_OUTPUT").

        Invalid outputs are retried up to `max_attempts` model calls (default 1 + max_retries).
        """
        model = model or self.config.model
        max_attempts = max_attempts or (1 + self.config.max_retries)
        json_schema = strict_schema(schema.model_json_schema())
        total, latency, calls = Usage(), 0.0, 0
        while calls < max_attempts:
            mode = VALIDATED_RETRY_FALLBACK if self.schema_support is False else BACKEND_CONSTRAINED
            try:
                if mode == BACKEND_CONSTRAINED:
                    res = self.chat(messages, model=model, max_tokens=max_tokens, temperature=temperature,
                                    response_format={"type": "json_schema", "json_schema": {
                                        "name": schema.__name__, "schema": json_schema, "strict": True}})
                    self.schema_support = True
                else:
                    res = self.chat(_fallback_messages(messages, json_schema), model=model,
                                    max_tokens=max_tokens, temperature=temperature)
            except InferenceError as e:
                if e.code == "BAD_REQUEST" and mode == BACKEND_CONSTRAINED:
                    log.warning("backend json_schema rejected; switching to %s", VALIDATED_RETRY_FALLBACK)
                    self.schema_support = False
                    continue
                raise
            calls += 1
            total, latency = total + res.usage, latency + res.latency_s
            try:
                value = schema.model_validate_json(extract_json(res.text))
            except (ValidationError, ValueError):
                self.meter.record(model, invalid=True)
                log.warning("schema-invalid output model=%s schema=%s call=%d finish_reason=%s",
                            model, schema.__name__, calls, res.finish_reason)
                continue
            return JsonResult(value, mode, model, total, latency, calls)
        raise InferenceError("BAD_OUTPUT", f"No schema-valid output after {calls} calls.")

    def stream(self, messages: list[dict], *, model: str | None = None, max_tokens: int = 512,
               temperature: float = 0.2) -> Iterator[str]:
        """Yield content deltas. Not retried (a partial stream cannot be replayed safely)."""
        self._require_enabled()
        model = model or self.config.model
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                   "stream": True, "stream_options": {"include_usage": True}}
        t0, ttft, usage = time.perf_counter(), None, Usage()
        try:
            with self._sem, self._http.stream("POST", "/chat/completions", json=payload) as r:
                if r.status_code >= 400:
                    r.read()
                    raise _status_error(r)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    if obj.get("usage"):
                        usage = Usage(obj["usage"].get("prompt_tokens") or 0,
                                      obj["usage"].get("completion_tokens") or 0)
                    for ch in obj.get("choices") or []:
                        delta = (ch.get("delta") or {}).get("content")
                        if delta:
                            ttft = ttft if ttft is not None else time.perf_counter() - t0
                            yield delta
        except httpx.TimeoutException:
            self.meter.record(model, failed=True)
            raise InferenceError("TIMEOUT", "Inference stream timed out.", True)
        except httpx.TransportError:
            self.meter.record(model, failed=True)
            raise InferenceError("UNAVAILABLE", "Inference endpoint unreachable.", True)
        except InferenceError:
            self.meter.record(model, failed=True)
            raise
        self.meter.record(model, usage=usage, latency_s=time.perf_counter() - t0, ttft_s=ttft)

    def list_models(self) -> list[str]:
        self._require_enabled()
        try:
            r = self._http.get("/models")
        except httpx.TimeoutException:
            raise InferenceError("TIMEOUT", "Inference request timed out.", True)
        except httpx.TransportError:
            raise InferenceError("UNAVAILABLE", "Inference endpoint unreachable.", True)
        if r.status_code >= 400:
            raise _status_error(r)
        return [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]

    def probe(self, model: str | None = None) -> dict:
        """Opt-in capability probe with a fictional prompt. Each feature is
        reported as supported / unsupported / unknown, with error codes only."""
        model = model or self.config.model
        report: dict = {"config": self.config.redacted(), "model": model}
        if not self.config.enabled:
            return report | {"status": "disabled"}

        def guarded(fn):
            try:
                return fn()
            except InferenceError as e:
                return {"status": "unsupported" if e.code in ("BAD_REQUEST", "NOT_FOUND") else "unknown",
                        "error": e.code}

        def models():
            ids = self.list_models()
            return {"status": "supported", "ids": ids, "model_listed": model in ids}

        def plain():
            r = self.chat([{"role": "user", "content": "Reply with the single word OK."}], model=model, max_tokens=5)
            return {"status": "supported" if r.text.strip() else "unknown", "latency_s": round(r.latency_s, 3)}

        def constrained():
            class _Probe(BaseModel):
                category: Literal["direct_match", "related_capability", "insufficient_evidence"]

            prev, self.schema_support = self.schema_support, None
            try:
                r = self.complete_json([{"role": "user", "content": "A lab builds glucose sensors. Need: wearable "
                                         "glucose sensing. Classify the match."}], _Probe, model=model,
                                       max_tokens=200, max_attempts=1)
                return {"status": "supported" if r.decoding_mode == BACKEND_CONSTRAINED else "unsupported",
                        "decoding_mode": r.decoding_mode}
            finally:
                if self.schema_support is None:
                    self.schema_support = prev

        def streaming():
            t0 = time.perf_counter()
            chunks = list(self.stream([{"role": "user", "content": "Count from 1 to 5."}], model=model, max_tokens=30))
            return {"status": "supported" if len(chunks) > 1 else "unknown", "chunks": len(chunks),
                    "total_s": round(time.perf_counter() - t0, 3)}

        report["models"] = guarded(models)
        report["plain"] = guarded(plain)
        report["json_schema"] = guarded(constrained)
        report["streaming"] = guarded(streaming)
        return report


def strict_schema(schema: dict) -> dict:
    """Copy of a JSON schema with `additionalProperties: false` on every object.

    Observed on Keera (T03 follow-up): without it, constrained decoding lets the
    model add unrequested keys (e.g. a long "explanation"), wasting tokens and
    truncating output at max_tokens.
    """
    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items()}
            if node.get("type") == "object" or "properties" in node:
                node.setdefault("additionalProperties", False)
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(schema)


def _fallback_messages(messages: list[dict], json_schema: dict) -> list[dict]:
    instruction = ("\n\nRespond with only one JSON object that matches this JSON schema. "
                   f"No prose, no code fences.\n{json.dumps(json_schema)}")
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = f"{m['content']}{instruction}"
            break
    else:
        out.append({"role": "user", "content": instruction.strip()})
    return out


_default: ApertusClient | None = None
_default_lock = threading.Lock()


def get_client() -> ApertusClient:
    """Process-wide client built from environment variables."""
    global _default
    with _default_lock:
        if _default is None:
            _default = ApertusClient()
        return _default
