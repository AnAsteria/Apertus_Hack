"""T05 inference adapter against a deterministic FAKE endpoint (httpx.MockTransport).

These tests say nothing about the real Keera gateway; see test_live.py (opt-in).
"""
import json
import logging
import os
import sys
import threading
import time

import httpx
import pytest
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.ai.client import (BACKEND_CONSTRAINED, VALIDATED_RETRY_FALLBACK, ApertusClient, InferenceError,
                           extract_json)
from app.ai.config import ConfigError, InferenceConfig

FAKE_KEY = "sk-test-not-a-real-key-123"
MSG = [{"role": "user", "content": "Fictional company: wearable glucose monitor."}]


class Needs(BaseModel):
    needs: list[str]


def completion(content, prompt=10, completion_tokens=5):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion_tokens}}


def make(handler, **cfg):
    config = InferenceConfig(base_url="https://fake.test/api/v1", api_key=FAKE_KEY,
                             **({"max_retries": 2, "backoff_base_s": 0.0} | cfg))
    return ApertusClient(config, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def scripted(*responses):
    """Handler returning the given (status, body) pairs in order and recording requests."""
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        status, body = responses[min(len(calls), len(responses)) - 1]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, json=body)

    handler.calls = calls
    return handler


# --- configuration --------------------------------------------------------------
def test_missing_key_disables_inference_without_network():
    h = scripted((200, completion("x")))
    c = ApertusClient(InferenceConfig(api_key=None), transport=httpx.MockTransport(h))
    with pytest.raises(InferenceError) as e:
        c.chat(MSG)
    assert e.value.code == "DISABLED" and h.calls == []


def test_config_from_env_and_validation():
    cfg = InferenceConfig.from_env({"APERTUS_API_KEY": FAKE_KEY, "APERTUS_BASE_URL": "http://localhost:8080/v1/",
                                    "APERTUS_MAX_CONCURRENCY": "2"})
    assert cfg.enabled and cfg.is_local and cfg.base_url == "http://localhost:8080/v1"
    assert cfg.max_concurrency == 2 and cfg.model == "apertus-v1-5-8b"
    with pytest.raises(ConfigError):
        InferenceConfig.from_env({"APERTUS_TIMEOUT_S": "soon"})
    with pytest.raises(ConfigError):
        InferenceConfig(max_concurrency=0)


def test_key_never_in_repr_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG, logger="bernmatch.inference")
    c = make(scripted((401, {"error": {"message": f"bad key {FAKE_KEY}"}})))
    assert FAKE_KEY not in repr(c) and FAKE_KEY not in repr(c.config) and FAKE_KEY not in str(c.config.redacted())
    with pytest.raises(InferenceError) as e:
        c.chat(MSG)
    assert FAKE_KEY not in str(e.value)
    assert FAKE_KEY not in caplog.text and "glucose" not in caplog.text


def test_authorization_header_sent():
    h = scripted((200, completion("ok")))
    make(h).chat(MSG)
    assert h.calls[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert str(h.calls[0].url) == "https://fake.test/api/v1/chat/completions"


# --- chat, retries and failures -------------------------------------------------
def test_chat_returns_text_usage_and_meters():
    c = make(scripted((200, completion("hello", 12, 3))))
    r = c.chat(MSG)
    assert r.text == "hello" and r.usage.prompt_tokens == 12 and r.attempts == 1
    snap = c.meter.snapshot()["apertus-v1-5-8b"]
    assert snap["calls"] == 1 and snap["completion_tokens"] == 3 and snap["samples"] == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_status_then_success(status):
    h = scripted((status, {"error": {}}), (200, completion("ok")))
    c = make(h)
    assert c.chat(MSG).attempts == 2
    assert c.meter.snapshot()["apertus-v1-5-8b"]["retries"] == 1


def test_rate_limit_exhausts_bounded_retries():
    h = scripted((429, {"error": {}}))
    with pytest.raises(InferenceError) as e:
        make(h, max_retries=2).chat(MSG)
    assert e.value.code == "RATE_LIMITED" and len(h.calls) == 3


def test_retry_after_header_respected_and_capped():
    slept = []
    h = lambda req: httpx.Response(429, headers={"retry-after": "120"}, json={}) if not slept else \
        httpx.Response(200, json=completion("ok"))
    c = ApertusClient(InferenceConfig(base_url="https://fake.test/v1", api_key=FAKE_KEY, max_retries=1),
                      transport=httpx.MockTransport(h), sleep=slept.append)
    c.chat(MSG)
    assert slept == [c.config.backoff_max_s]


@pytest.mark.parametrize("status,code", [(401, "AUTH"), (403, "AUTH"), (404, "NOT_FOUND"), (400, "BAD_REQUEST")])
def test_non_retryable_errors_fail_fast(status, code):
    h = scripted((status, {"error": {}}))
    with pytest.raises(InferenceError) as e:
        make(h).chat(MSG)
    assert e.value.code == code and len(h.calls) == 1


def test_timeout_and_unreachable_fail_safely():
    with pytest.raises(InferenceError) as e:
        make(scripted((0, httpx.ReadTimeout("slow")))).chat(MSG)
    assert e.value.code == "TIMEOUT"
    with pytest.raises(InferenceError) as e:
        make(scripted((0, httpx.ConnectError("down")))).chat(MSG)
    assert e.value.code == "UNAVAILABLE"


def test_malformed_response_body_is_unavailable_not_crash():
    with pytest.raises(InferenceError) as e:
        make(scripted((200, {"unexpected": True}))).chat(MSG)
    assert e.value.code == "UNAVAILABLE"


def test_concurrency_cap_is_enforced():
    active, peak, lock = [0], [0], threading.Lock()

    def handler(req):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return httpx.Response(200, json=completion("ok"))

    c = make(handler, max_concurrency=2)
    threads = [threading.Thread(target=c.chat, args=(MSG,)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 2


# --- structured output ------------------------------------------------------------
def test_backend_constrained_mode_sends_schema():
    h = scripted((200, completion('{"needs": ["CGM"]}')))
    c = make(h)
    r = c.complete_json(MSG, Needs)
    assert r.value.needs == ["CGM"] and r.decoding_mode == BACKEND_CONSTRAINED
    body = json.loads(h.calls[0].content)
    assert body["response_format"]["type"] == "json_schema"
    sent = body["response_format"]["json_schema"]["schema"]
    assert sent["required"] == ["needs"] and sent["additionalProperties"] is False


def test_strict_schema_closes_nested_objects():
    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner
        items: list[Inner]

    from app.ai.client import strict_schema
    s = strict_schema(Outer.model_json_schema())
    assert s["additionalProperties"] is False
    assert s["$defs"]["Inner"]["additionalProperties"] is False


def test_rejected_schema_falls_back_and_is_labelled_weaker():
    h = scripted((400, {"error": {"message": "response_format not supported"}}),
                 (200, completion('Here you go:\n```json\n{"needs": ["biosensing"]}\n```')))
    c = make(h)
    r = c.complete_json(MSG, Needs)
    assert r.decoding_mode == VALIDATED_RETRY_FALLBACK and r.value.needs == ["biosensing"]
    assert c.schema_support is False
    fallback_body = json.loads(h.calls[1].content)
    assert "response_format" not in fallback_body
    assert "JSON schema" in fallback_body["messages"][-1]["content"]


def test_invalid_output_retried_then_accepted():
    h = scripted((200, completion("not json")), (200, completion('{"needs": []}')))
    c = make(h)
    r = c.complete_json(MSG, Needs)
    assert r.attempts == 2 and r.usage.prompt_tokens == 20
    assert c.meter.snapshot()["apertus-v1-5-8b"]["invalid_outputs"] == 1


def test_persistently_invalid_output_raises_bad_output():
    h = scripted((200, completion('{"wrong": 1}')))
    with pytest.raises(InferenceError) as e:
        make(h).complete_json(MSG, Needs, max_attempts=3)
    assert e.value.code == "BAD_OUTPUT" and len(h.calls) == 3


def test_extract_json_handles_prose_and_fences():
    assert json.loads(extract_json('Sure! {"a": 1} hope that helps')) == {"a": 1}
    assert json.loads(extract_json('```json\n{"a": {"b": 2}}\n```')) == {"a": {"b": 2}}


# --- streaming ----------------------------------------------------------------------
def _sse(*objs):
    lines = [f"data: {json.dumps(o)}" for o in objs] + ["data: [DONE]"]
    return ("\n\n".join(lines) + "\n\n").encode()


def test_stream_yields_deltas_and_records_usage():
    body = _sse({"choices": [{"delta": {"content": "Hel"}}]}, {"choices": [{"delta": {"content": "lo"}}]},
                {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    h = lambda req: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    c = make(h)
    assert "".join(c.stream(MSG)) == "Hello"
    snap = c.meter.snapshot()["apertus-v1-5-8b"]
    assert snap["completion_tokens"] == 2 and snap["ttft_median_s"] is not None


def test_stream_error_status_raises_before_any_delta():
    c = make(scripted((503, {"error": {}})))
    with pytest.raises(InferenceError) as e:
        list(c.stream(MSG))
    assert e.value.code == "UNAVAILABLE"


# --- probe ----------------------------------------------------------------------------
def test_probe_reports_capabilities_without_secrets():
    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "apertus-v1-5-8b"}]})
        body = json.loads(req.content)
        if body.get("stream"):
            return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "1"}}]},
                                                    {"choices": [{"delta": {"content": "2"}}]}))
        if "response_format" in body:
            return httpx.Response(400, json={"error": {}})
        return httpx.Response(200, json=completion('{"category": "direct_match"}'))

    report = make(handler).probe()
    assert report["models"]["model_listed"] is True
    assert report["plain"]["status"] == "supported"
    assert report["json_schema"] == {"status": "unsupported", "decoding_mode": VALIDATED_RETRY_FALLBACK}
    assert report["streaming"]["status"] == "supported"
    assert FAKE_KEY not in json.dumps(report)


def test_probe_disabled_without_key():
    assert ApertusClient(InferenceConfig(api_key=None)).probe()["status"] == "disabled"
