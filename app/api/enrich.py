"""Glue between search and the enrichment stream (T18 integration; the stream itself is
app/api/enrichment.py, the interpretation is app/ai/interpret.py, both by Ruihan).

This module only (1) sets `enrichment_state` honestly on the search response and (2) provides a
SYNTHETIC interpreter for fixture mode, so the UI can be exercised without a model. Nothing here
calls an endpoint.
"""
import os

from ..ai.config import InferenceConfig
from ..ai.interpret import Interpretation
from ..contracts import Need, SearchRequest


def fixture_mode() -> bool:
    return os.environ.get("BERNMATCH_FIXTURE_MODE") == "1"


def available() -> bool:
    """Enrichment can run when a real key is configured, or in fixture mode (synthetic)."""
    return fixture_mode() or InferenceConfig.from_env().enabled


def apply_state(response: dict, req: SearchRequest) -> dict:
    """`pending` only if something can actually produce events; otherwise `unavailable`."""
    if req.enrichment_requested:
        response["enrichment_state"] = "pending" if available() else "unavailable"
    return response


def fixture_interpreter(req: SearchRequest) -> Interpretation:
    """SYNTHETIC. A re-run (needs given) echoes the analyst's needs and adds no new suggestions."""
    if req.needs:
        needs = [n for n in req.needs if n.origin == "user"]
    else:
        needs = [Need(schema_version="1", need_id="need_s_synthetic1",
                      text="continuous monitoring technology (synthetic suggestion)",
                      origin="suggested", kind="competency")]
    return Interpretation(needs=needs,
                          expanded_queries=[{"language": "de", "text": "Bildgebung (synthetic)", "source": req.query}],
                          clarification=None, partner_type=None, decoding_mode="synthetic")
