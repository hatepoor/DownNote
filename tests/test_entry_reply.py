"""条目回应数据层（v0.3.0 01）：建库、一 entry 一回应、转移标记。"""
import pytest

from down_note.db import database, models


@pytest.fixture()
def db(tmp_path):
    database.ensureSchema(tmp_path / "t.db")
    with database.getDb(tmp_path / "t.db") as session:
        yield session


def _entry(db) -> int:
    return models.addEntry(db, "今天有点累", None, "2026-10-13T15:42:00")


def test_create_and_get(db):
    entryId = _entry(db)
    reply = models.createEntryReply(db, entryId, "累了就早点休息。")
    assert reply is not None
    got = models.getReplyByEntry(db, entryId)
    assert got is not None and got.reply_text == "累了就早点休息。"


def test_one_reply_per_entry(db):
    entryId = _entry(db)
    assert models.createEntryReply(db, entryId, "第一句") is not None
    assert models.createEntryReply(db, entryId, "第二句") is None  # 已存在则拒


def test_mark_transferred(db):
    entryId = _entry(db)
    reply = models.createEntryReply(db, entryId, "一句")
    models.markReplyTransferred(db, reply.id, "sess-1", 42)
    got = models.getReplyByEntry(db, entryId)
    assert got.session_id == "sess-1" and got.session_message_id == 42


def test_schema_version_bumped():
    assert database.SCHEMA_VERSION >= 8
