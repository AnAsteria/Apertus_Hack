"""OPT-IN live checks against the real endpoint. Skipped unless BERNMATCH_LIVE_TESTS=1
and APERTUS_API_KEY is set. Fictional prompts only. Never run in routine CI.

    BERNMATCH_LIVE_TESTS=1 python -m pytest tests/ai/test_live.py -q -s
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.ai.client import ApertusClient
from app.ai.config import InferenceConfig

pytestmark = pytest.mark.skipif(
    os.environ.get("BERNMATCH_LIVE_TESTS") != "1" or not os.environ.get("APERTUS_API_KEY"),
    reason="live inference tests are opt-in (BERNMATCH_LIVE_TESTS=1 and APERTUS_API_KEY)")


@pytest.fixture(scope="module")
def client():
    c = ApertusClient(InferenceConfig.from_env())
    yield c
    c.close()


def test_live_probe(client):
    report = client.probe()
    print(json.dumps(report, indent=2))
    assert report["models"]["status"] == "supported" and report["models"]["model_listed"]
    assert report["plain"]["status"] == "supported"
    assert report["json_schema"]["status"] in ("supported", "unsupported")
    assert report["streaming"]["status"] in ("supported", "unknown")
    print(json.dumps(client.meter.snapshot(), indent=2))
