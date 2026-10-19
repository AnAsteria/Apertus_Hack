"""EXTRA A1: optional cross-encoder rerank (synthetic model, no weights, no network)."""
import numpy as np
from app.search import rerank as R


class FakeCE:
    def __init__(self, prefer):
        self.prefer, self.calls = prefer, 0

    def score(self, query, texts):
        self.calls += 1
        return np.array([5.0 if self.prefer in t else -5.0 for t in texts], dtype=np.float32)


def test_rerank_reorders_only_the_top_candidates():
    fused = {'a': .03, 'b': .02, 'c': .01, 'd': .005}
    texts = {'a': 'news page', 'b': 'insulin decision support group', 'c': 'other', 'd': 'insulin'}
    out = R.rerank(fused, texts, 'insulin decision support', FakeCE('insulin decision'), top_n=3)
    assert set(out) == {'a', 'b', 'c'}          # 'd' was outside the top 3: dropped, not promoted
    assert max(out, key=out.get) == 'b' and all(0 < v < 1 for v in out.values())


def test_missing_or_broken_model_disables_rerank(monkeypatch, tmp_path):
    monkeypatch.delenv('BERNMATCH_RERANK_DIR', raising=False)
    assert R.load_from_env() is None
    monkeypatch.setenv('BERNMATCH_RERANK_DIR', str(tmp_path))  # empty dir: no model files
    assert R.load_from_env() is None
