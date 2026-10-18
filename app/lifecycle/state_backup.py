"""T33: keep feedback and admin job records across Space restarts.

The live SQLite file stays on the container's local disk (a live database does not belong
on a mounted bucket). This module copies a consistent snapshot of it to the bucket and puts
it back on start-up:

    python -m app.lifecycle.state_backup restore --db $SERVE/bernmatch.sqlite --store /data/state
    python -m app.lifecycle.state_backup backup  --db $SERVE/bernmatch.sqlite --store /data/state

`backup` uses SQLite's online backup API, so a snapshot taken while the app writes is still a
valid database. It writes to a temporary file and renames it, so a crash mid-copy never leaves
a broken snapshot behind. `restore` never overwrites a database that already exists locally.
Anything written after the last snapshot is lost on restart; the interval bounds that loss.
"""
import argparse
import os
import sqlite3
import sys

SNAPSHOT = "bernmatch.sqlite"


def backup(db: str, store: str) -> bool:
    """Snapshot `db` into `store`. Returns False (and does nothing) when `db` does not exist."""
    if not os.path.exists(db):
        return False
    os.makedirs(store, exist_ok=True)
    final = os.path.join(store, SNAPSHOT)
    tmp = final + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    src = sqlite3.connect(db)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    os.replace(tmp, final)
    return True


def restore(db: str, store: str) -> bool:
    """Copy the snapshot back to `db` if there is one and `db` does not exist yet."""
    snap = os.path.join(store, SNAPSHOT)
    if os.path.exists(db) or not os.path.exists(snap):
        return False
    os.makedirs(os.path.dirname(db) or ".", exist_ok=True)
    src = sqlite3.connect(snap)
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("snapshot failed the integrity check; not restored")
        dst = sqlite3.connect(db)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("action", choices=["backup", "restore"])
    p.add_argument("--db", required=True)
    p.add_argument("--store", required=True)
    a = p.parse_args(argv)
    done = (backup if a.action == "backup" else restore)(a.db, a.store)
    print(f"state {a.action}: {'done' if done else 'nothing to do'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
