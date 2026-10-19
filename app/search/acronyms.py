"""EXTRA A4: acronym <-> long form pairs mined from stored sentences ('continuous glucose
monitoring (CGM)'). Keyword channel only: the other form is added as extra BM25 terms; dense
retrieval already handles meaning. No LLM, no network. Cached as JSON next to the served index."""
from __future__ import annotations

import json
import os
import re
import threading
from collections import Counter, defaultdict
from pathlib import Path

PAIR = re.compile(r'((?:[A-Za-zÄÖÜäöüßéèàç][\w\-]*\s+){1,7}[A-Za-zÄÖÜäöüßéèàç][\w\-]*)\s+\(([A-Z][A-Za-z0-9]{1,7})\)')
MIN_COUNT = 2


def mine(texts) -> dict[str, str]:
    """acronym -> most frequent long form whose word initials spell it (seen >= MIN_COUNT times)."""
    counts = Counter()
    for text in texts:
        for m in PAIR.finditer(text):
            words, ab = m.group(1).split(), m.group(2)
            for k in range(len(words)):
                tail = words[k:]
                if ''.join(w[0] for w in tail).upper() == ab.upper():
                    counts[(ab, ' '.join(tail))] += 1
                    break
    best = defaultdict(lambda: ('', 0))
    for (ab, long), n in counts.items():
        if n >= MIN_COUNT and n > best[ab][1]:
            best[ab] = (long, n)
    return {ab: long for ab, (long, _) in best.items()}


class AcronymTable:
    def __init__(self, store, cache_dir):
        self.pairs: dict[str, str] = {}
        self.long_to_ab: dict[str, str] = {}
        self.ready = False
        cache = Path(cache_dir) / ('acronyms.' + store.root.name + '.json')
        threading.Thread(target=self._load, args=(store, cache), daemon=True).start()

    def _load(self, store, cache):
        try:
            if cache.exists():
                pairs = json.loads(cache.read_text())
            else:
                with store.connect() as db:
                    pairs = mine(json.loads(b)['text'] for (b,) in db.execute('SELECT body FROM sentences'))
                tmp = cache.with_suffix('.tmp')
                tmp.write_text(json.dumps(pairs, ensure_ascii=False))
                os.replace(tmp, cache)
            self.pairs = pairs
            self.long_to_ab = {v.casefold(): k for k, v in pairs.items()}
            self.ready = True
        except Exception:
            self.ready = False  # never breaks search

    def variants(self, query: str) -> list[str]:
        """Other forms to add to the keyword search for this query."""
        if not self.ready:
            return []
        out = [self.pairs[tok] for tok in re.findall(r'\b[A-Z][A-Za-z0-9]{1,7}\b', query) if tok in self.pairs]
        q = query.casefold()
        out += [ab for long, ab in self.long_to_ab.items() if long in q]
        return list(dict.fromkeys(out))
