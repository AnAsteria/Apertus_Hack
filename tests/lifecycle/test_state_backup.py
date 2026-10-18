"""T33: feedback written before a restart is still readable after it (simulated restart)."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.contracts import Feedback
from app.lifecycle import state_backup
from app.repository import SqliteRepository


def _fb(key):
    return Feedback(schema_version="1", request_id="r1", revision=1, entity_id="ent_1",
                    action="select", idempotency_key=key)


def _count(db):
    with sqlite3.connect(db) as c:
        return c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]


def test_feedback_survives_a_restart(tmp_path):
    store = tmp_path / "bucket" / "state"
    disk1 = tmp_path / "container1" / "bernmatch.sqlite"
    os.makedirs(disk1.parent)
    repo = SqliteRepository(str(disk1)); repo.init()
    repo.put_feedback(_fb("k1")); repo.put_feedback(_fb("k2"))
    assert state_backup.backup(str(disk1), str(store))

    # restart: a new container with an empty local disk
    disk2 = tmp_path / "container2" / "bernmatch.sqlite"
    assert state_backup.restore(str(disk2), str(store))
    assert _count(disk2) == 2
    # idempotency survives too: the same key with the same body is not stored twice
    repo2 = SqliteRepository(str(disk2)); repo2.init()
    assert repo2.put_feedback(_fb("k1"))[1] is False


def test_restore_never_overwrites_a_live_database(tmp_path):
    store = tmp_path / "state"
    old = tmp_path / "old.sqlite"
    repo = SqliteRepository(str(old)); repo.init(); repo.put_feedback(_fb("old"))
    state_backup.backup(str(old), str(store))
    live = tmp_path / "live.sqlite"
    repo = SqliteRepository(str(live)); repo.init(); repo.put_feedback(_fb("a")); repo.put_feedback(_fb("b"))
    assert state_backup.restore(str(live), str(store)) is False
    assert _count(live) == 2


def test_nothing_to_do_without_files(tmp_path):
    assert state_backup.backup(str(tmp_path / "missing.sqlite"), str(tmp_path / "s")) is False
    assert state_backup.restore(str(tmp_path / "db.sqlite"), str(tmp_path / "s")) is False
    assert not (tmp_path / "s").exists()


def test_corrupt_snapshot_is_refused(tmp_path):
    store = tmp_path / "state"; os.makedirs(store)
    (store / state_backup.SNAPSHOT).write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(Exception):
        state_backup.restore(str(tmp_path / "db.sqlite"), str(store))
    assert not (tmp_path / "db.sqlite").exists() or os.path.getsize(tmp_path / "db.sqlite") == 0
