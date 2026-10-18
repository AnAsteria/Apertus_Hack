"""Purge suppressed content from the stored corpus (T12): the 30-day copy-removal step of docs/data-policy.md.

Serving and the crawler already honour the suppression list. This removes the stored copies from
`corpus.sqlite` (documents, versions, sentences, entities, cached pages, variants, labels) and
VACUUMs the file so the bytes are really gone. Dry-run by default.

NOT covered, on purpose and stated in the report: derived files outside the database
(`data/extraction/`, `data/knowledge/`, search indexes, exports) must be rebuilt from the purged
corpus, and backups made by anyone must be deleted by hand. Commit hashes of the suppression file
are the audit trail.
"""
import argparse
import json
import sys
from pathlib import Path

from . import serving, suppression

DERIVED = ("extraction", "knowledge", "index", "indexes", "exports")


def find_documents(db, data: dict) -> list[tuple[str, str]]:
    """(document_id, url) for every stored document whose URL, or any language-variant or
    cached-page URL, is suppressed."""
    docs = {row[0]: row[1] for row in db.execute("SELECT id, url FROM documents")}
    urls: dict[str, set] = {d: {u} for d, u in docs.items()}
    for d, u in db.execute("SELECT document_id, url FROM variants"):
        urls.setdefault(d, set()).add(u)
    for u, d in db.execute("SELECT url, document_id FROM pages"):
        urls.setdefault(d, set()).add(u)
    return sorted((d, docs.get(d, "")) for d, us in urls.items()
                  if any(suppression.is_suppressed_url(data, u) for u in us if u))


def purge(data_dir: str, data: dict, apply: bool = False) -> dict:
    import sqlite3
    path = Path(data_dir) / "corpus.sqlite"
    if not path.exists():
        return {"corpus": "none", "documents": 0, "applied": False}
    db = sqlite3.connect(path)
    try:
        victims = find_documents(db, data)
        counts = {"documents": len(victims), "versions": 0, "sentences": 0, "entities": 0, "pages": 0}
        for doc_id, _ in victims:
            vers = [r[0] for r in db.execute("SELECT id FROM versions WHERE document_id=?", (doc_id,))]
            counts["versions"] += len(vers)
            for v in vers:
                counts["sentences"] += db.execute("SELECT COUNT(*) FROM sentences WHERE version_id=?", (v,)).fetchone()[0]
            counts["entities"] += db.execute("SELECT COUNT(*) FROM entities WHERE document_id=?", (doc_id,)).fetchone()[0]
            counts["pages"] += db.execute("SELECT COUNT(*) FROM pages WHERE document_id=?", (doc_id,)).fetchone()[0]
            if apply:
                for v in vers:
                    db.execute("DELETE FROM passage_entities WHERE passage_id LIKE ?", (v + ":p%",))
                    db.execute("DELETE FROM sentences WHERE version_id=?", (v,))
                for table in ("versions", "entities", "pages", "variants", "labels", "active_versions"):
                    col = "id" if table == "documents" else "document_id"
                    db.execute(f"DELETE FROM {table} WHERE {col}=?", (doc_id,))
                db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        if apply:
            db.commit()
            db.execute("VACUUM")
    finally:
        db.close()
    rebuild = [d for d in DERIVED if (Path(data_dir) / d).exists()]
    return {"corpus": str(path), "applied": apply, **counts,
            "removed_urls": [u for _, u in victims],
            "must_rebuild_by_hand": rebuild,
            "note": "Derived files and backups are not touched; rebuild them from the purged corpus and delete backups."}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.lifecycle.purge")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--suppression", default=None, help="defaults to config/suppression.json")
    ap.add_argument("--apply", action="store_true", help="delete; without it only reports what would go")
    a = ap.parse_args(argv)
    data = suppression.load(a.suppression) if a.suppression else serving.load_suppression()
    print(json.dumps(purge(a.data_dir, data, apply=a.apply), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
