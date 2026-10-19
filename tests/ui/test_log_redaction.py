"""EXTRA F3: query and company text never reach application logs (data policy: no company input in logs)."""
import logging
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import main
from app.api import enrich, enrichment, search as search_api

MARK_Q = "ZZQUERYMARK4711"
MARK_C = "ZZCOMPANYSECRET0815"


def test_search_and_enrichment_never_log_query_or_company_text(monkeypatch, tmp_path, caplog, capsys):
    monkeypatch.setenv("BERNMATCH_FIXTURE_MODE", "1")
    monkeypatch.setenv("BERNMATCH_DATA_DIR", str(tmp_path))
    enrichment.registry.clear()
    enrichment.set_interpreter(enrich.fixture_interpreter)
    caplog.set_level(logging.DEBUG)
    try:
        client = TestClient(main.app)
        body = {"schema_version": "1", "query": f"imaging {MARK_Q}", "revision": 1, "entity_type": None,
                "company_context": f"We build sensors. {MARK_C}", "needs": [], "enrichment_requested": True}
        r = client.post("/api/v1/search", json=body)
        assert r.status_code == 200
        rid = r.json()["request_id"]
        start = client.post(f"/api/v1/search/{rid}/enrichment", json=body).json()
        client.get(start["events_url"])
        # Error paths must not echo input either.
        client.post("/api/v1/search", json={**body, "query": "x" * 5000 + MARK_Q})       # 413
        client.post("/api/v1/search", json={**body, "unknown_field": MARK_Q})             # 422
        client.post("/api/v1/feedback", json={"schema_version": "1", "request_id": rid, "revision": 1,
                                               "entity_id": "ent_x", "action": "relevant",
                                               "idempotency_key": "k1", "comment": MARK_C})
    finally:
        enrichment.set_interpreter(None)
        search_api.set_backend(None)
    out = capsys.readouterr()
    logged = caplog.text + out.out + out.err
    assert MARK_Q not in logged and MARK_C not in logged
