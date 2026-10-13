"""条目回应生成链路（v0.3.0 01）：开关、降级、唯一、提示词装配。

隔离由 tests/conftest.py 的 autouse 夹具 isolateDataDir 保证；种子用无参 getDb()，
调 generateEntryReply 不传 dbPath（默认库=隔离库）。人格测试写 tmp_path/soul.md 触发
（config.getDataDir 已被夹具指向 tmp_path）。
"""
import pytest

from down_note.core import entryReply
from down_note.db import database, models


@pytest.fixture(autouse=True)
def _schema(dbFile):
    """建好隔离库的表（conftest 的 dbFile 建表；本文件全部用例都要写库）。"""
    return dbFile


def _setup(monkeypatch, reply_text="抱抱，先喝口水。"):
    captured = {}

    def fakeInvoke(cfg, messages, *, profile="chat"):
        captured["system"] = messages[0].content
        return reply_text

    monkeypatch.setattr(entryReply.llm, "invokeModel", fakeInvoke)
    with database.getDb() as db:
        models.setSetting(db, "base_url", "http://x/v1")
        models.setSetting(db, "model_name", "m")
        entryId = models.addEntry(db, "今天面试砸了，胸口很闷。", None, "2026-10-13T15:42:00")
        models.upsertMood(db, entryId=entryId, labels=["低落"], intensity=7,
                          summary="面试砸了很闷", crisis=False,
                          analyzedAt="2026-10-13T15:42:05", model="m")
    return entryId, captured


def test_reply_generated_and_stored(monkeypatch):
    entryId, captured = _setup(monkeypatch)
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        got = models.getReplyByEntry(db, entryId)
    assert got is not None and got.reply_text == "抱抱，先喝口水。"
    assert "低落" in captured["system"] and "面试砸了" in captured["system"]


def test_disabled_switch_skips(monkeypatch):
    entryId, _ = _setup(monkeypatch)
    with database.getDb() as db:
        models.setSetting(db, "diary_reply_enabled", "0")
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        assert models.getReplyByEntry(db, entryId) is None


def test_unconfigured_model_skips(monkeypatch):
    with database.getDb() as db:  # 不配模型
        entryId = models.addEntry(db, "x", None, "2026-10-13T15:42:00")
        models.upsertMood(db, entryId=entryId, labels=["平静"], intensity=3,
                          summary="普通", crisis=False, analyzedAt="x", model="m")
    monkeypatch.setattr(entryReply.llm, "invokeModel",
                        lambda *a, **k: pytest.fail("降级下不应调模型"))
    entryReply.generateEntryReply(entryId)
    with database.getDb() as db:
        assert models.getReplyByEntry(db, entryId) is None


def test_persona_injected(monkeypatch, tmp_path):
    entryId, captured = _setup(monkeypatch)
    with database.getDb() as db:
        models.setSetting(db, "persona_enabled", "1")
    (tmp_path / "soul.md").write_text("说话像损友，爱怼人。", encoding="utf-8")
    entryReply.generateEntryReply(entryId)
    assert "损友" in captured["system"]
