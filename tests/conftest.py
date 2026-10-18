import pytest


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """The suite sends far more than a real client per minute; tests of the limit turn it on."""
    monkeypatch.setenv("BERNMATCH_RATE_LIMIT_PER_MIN", "0")
