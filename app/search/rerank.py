"""EXTRA A1: optional open cross-encoder rerank of the fused top candidates (CPU, ONNX).

Off unless `BERNMATCH_RERANK_DIR` points to a pinned model directory (model.onnx, tokenizer.json,
config.json, REVISION). No network at query time. The reranker only reorders candidates the
fast path already found; abstention and the answer outcome still come from retrieval signals.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

TOP_N = int(os.environ.get('BERNMATCH_RERANK_TOP', '30'))
MAX_TOKENS = 512


class CrossEncoder:
    def __init__(self, model_dir, threads=None):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.root = Path(model_dir)
        for name in ('model.onnx', 'tokenizer.json', 'config.json'):
            if not (self.root / name).is_file():
                raise FileNotFoundError(name)
        self.revision = (self.root / 'REVISION').read_text().strip() if (self.root / 'REVISION').exists() else None
        self.tokenizer = Tokenizer.from_file(str(self.root / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self.lock = threading.Lock()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or int(os.environ.get('BERNMATCH_ORT_THREADS', '4'))
        self.session = ort.InferenceSession(str(self.root / 'model.onnx'), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        self.inputs = {x.name for x in self.session.get_inputs()}

    def score(self, query: str, texts: list[str], batch_size: int = 16) -> np.ndarray:
        out = []
        for begin in range(0, len(texts), batch_size):
            with self.lock:
                enc = self.tokenizer.encode_batch([(query, t) for t in texts[begin:begin + batch_size]])
            width = max(len(e.ids) for e in enc)
            ids = np.ones((len(enc), width), dtype=np.int64)  # XLM-R pad id is 1
            mask = np.zeros_like(ids)
            for i, e in enumerate(enc):
                ids[i, :len(e.ids)] = e.ids
                mask[i, :len(e.ids)] = 1
            feed = {'input_ids': ids, 'attention_mask': mask}
            if 'token_type_ids' in self.inputs:
                feed['token_type_ids'] = np.zeros_like(ids)
            logits = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
            out.extend(np.asarray(logits, dtype=np.float32).reshape(len(enc), -1)[:, 0])
        return np.asarray(out, dtype=np.float32)


def load_from_env():
    path = os.environ.get('BERNMATCH_RERANK_DIR')
    if not path:
        return None
    try:
        return CrossEncoder(path)
    except Exception:
        return None  # a missing or broken reranker never breaks search


def rerank(fused: dict, texts: dict, query: str, model, top_n: int = TOP_N) -> dict:
    """Return new relevance scores for the top `top_n` fused entities (others dropped).
    Scores are the reranker's sigmoid, so MMR sees a 0..1 relevance scale."""
    top = sorted(fused, key=lambda e: (-fused[e], e))[:top_n]
    if not top:
        return fused
    logits = model.score(query, [texts[e] for e in top])
    return {e: float(1 / (1 + np.exp(-s))) for e, s in zip(top, logits)}
