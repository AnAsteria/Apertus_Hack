"""Fetch the pinned open cross-encoder (EXTRA A1) for a cloud deployment, once, at container start.

    python -m app.search.fetch_reranker --dest /home/user/work/rerank [--variant quint8_avx2]

Never called at query time and never in the air-gapped compose run (there the directory is
mounted ready-made or the reranker stays off). Writes model.onnx, tokenizer.json, config.json
and REVISION into --dest; exits non-zero on any failure, and search then runs without it.
"""
import argparse
import shutil
from pathlib import Path

REPO = 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1'
REVISION = '1427fd652930e4ba29e8149678df786c240d8825'  # same revision measured in A1 (#119)
VARIANTS = ('quint8_avx2', 'qint8_avx512_vnni', 'qint8_avx512', 'qint8_arm64')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dest', required=True)
    p.add_argument('--variant', default='quint8_avx2', choices=VARIANTS)
    a = p.parse_args()
    from huggingface_hub import hf_hub_download
    dest = Path(a.dest); dest.mkdir(parents=True, exist_ok=True)
    onnx = hf_hub_download(REPO, f'onnx/model_{a.variant}.onnx', revision=REVISION)
    shutil.copyfile(onnx, dest / 'model.onnx')
    for name in ('tokenizer.json', 'config.json'):
        shutil.copyfile(hf_hub_download(REPO, name, revision=REVISION), dest / name)
    (dest / 'REVISION').write_text(f'{REVISION} {a.variant}\n')
    print(f'reranker ready: {REPO}@{REVISION[:8]} {a.variant} -> {dest}')


if __name__ == '__main__':
    main()
