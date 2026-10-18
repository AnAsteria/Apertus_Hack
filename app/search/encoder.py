"""Local E5 ONNX CPU encoder, mean pooling + L2 normalization.

The operator supplies pinned model/tokenizer assets. Runtime never downloads.
Long passages use overlapping tokenizer overflow windows, retaining every token.
"""
import hashlib
import json
import os
import threading
from pathlib import Path
import numpy as np


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    if not np.isfinite(vectors).all():
        raise ValueError('nonfinite_embeddings')
    lengths = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if np.any(lengths < 1e-12):
        raise ValueError('zero_embedding')
    return vectors / lengths


class OnnxEncoder:
    def __init__(self, model_dir, threads=None):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.root = Path(model_dir)
        self.manifest = json.loads((self.root/'model_manifest.json').read_text())
        if self.manifest.get('license') != 'mit' or len(self.manifest.get('revision','')) != 40:
            raise ValueError('unpinned_model')
        if not {'model.onnx','tokenizer.json','config.json'} <= set(self.manifest['files']):
            raise ValueError('incomplete_model_manifest')
        for filename, asset in self.manifest['files'].items():
            if Path(filename).name != filename or digest(self.root/filename) != asset['sha256']:
                raise ValueError('model_asset_hash_mismatch')
        config = json.loads((self.root/'config.json').read_text())
        self.pad_id = config['pad_token_id']
        self.tokenizer = Tokenizer.from_file(str(self.root/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512, stride=64)
        self.lock = threading.Lock()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or int(os.environ.get('BERNMATCH_ORT_THREADS','4'))
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.root/'model.onnx'), sess_options=options,
                                           providers=['CPUExecutionProvider'])
        self.inputs = {x.name for x in self.session.get_inputs()}
        self.dimensions = int(self.session.get_outputs()[0].shape[-1])

    def encode_windows(self, texts, kind='passage', batch_size=16, progress=None):
        if kind not in ('query','passage'):
            raise ValueError('invalid_prefix')
        vectors, owners = [], []
        for begin in range(0, len(texts), batch_size):
            with self.lock:
                encodings = self.tokenizer.encode_batch([kind+': '+t for t in texts[begin:begin+batch_size]])
            flat, mapping = [], []
            for i, encoding in enumerate(encodings):
                windows = [encoding] + encoding.overflowing
                flat.extend(windows)
                mapping.extend([begin+i]*len(windows))
            for offset in range(0, len(flat), batch_size):
                batch = flat[offset:offset+batch_size]
                width = max(len(x.ids) for x in batch)
                ids = np.full((len(batch),width), self.pad_id, dtype=np.int64)
                mask = np.zeros_like(ids)
                types = np.zeros_like(ids)
                for i, enc in enumerate(batch):
                    n = len(enc.ids)
                    ids[i,:n] = enc.ids
                    mask[i,:n] = 1
                    types[i,:n] = enc.type_ids
                inputs = {'input_ids':ids, 'attention_mask':mask, 'token_type_ids':types}
                output = self.session.run(None, {k:v for k,v in inputs.items() if k in self.inputs})[0]
                weights = mask.astype(np.float32)
                pooled = (output * weights[...,None]).sum(axis=1) / weights.sum(axis=1,keepdims=True)
                vectors.extend(normalize(pooled))
                owners.extend(mapping[offset:offset+batch_size])
            if progress:
                progress(min(begin+batch_size,len(texts)),len(texts))
        if not vectors:
            return np.empty((0,self.dimensions),dtype=np.float32), np.empty(0,dtype=np.int32)
        return np.asarray(vectors,dtype=np.float32), np.asarray(owners,dtype=np.int32)

    def encode(self, texts, kind='query'):
        vectors, owners = self.encode_windows(texts, kind=kind)
        result = np.zeros((len(texts),self.dimensions),dtype=np.float32)
        for i, vector in zip(owners,vectors):
            result[i] += vector
        return normalize(result)
