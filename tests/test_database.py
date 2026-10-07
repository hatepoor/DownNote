"""数据库测试：建表、ORM 读写往返、级联删除、.env 密钥加载与掩码。

对应模块：docx/v0.1.0/modules/02-数据库与配置.md
"""

import os

from sqlalchemy import select, text

from down_note import config
from down_note.db import database, models


def test_schemaCreatedAndIdempotent(dbFile):
    with database.getDb(dbFile) as db:
        names = set(db.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars())
        assert {"entries", "moods", "messages", "settings"} <= names
    # 重复执行幂等
    database.ensureSchema(dbFile)


def test_entryAndMoodRoundtrip(dbFile):
    with database.getDb(dbFile) as db:
        entryId = models.addEntry(db, "今天有点低落", None, "2026-10-05T21:00:00")
        assert entryId == 1

        models.upsertMood(
                db,
                entryId=entryId,
                labels=["低落", "焦虑"],
                intensity=6,
                summary="工作不顺导致的心情低落",
                crisis=False,
                analyzedAt="2026-10-05T21:05:00",
                model="glm-5.3",
            )

        entry = models.getEntry(db, entryId)
        assert entry.content == "今天有点低落"
        assert entry.analyzed is False

        mood = models.getMoodByEntry(db, entryId)
        assert mood.intensity == 6
        assert mood.labels == '["低落", "焦虑"]'

        # 重分析走 UPDATE 覆盖，不新增行
        models.upsertMood(
                db,
                entryId=entryId,
                labels=["平静"],
                intensity=3,
                summary="睡了一觉好多了",
                crisis=False,
                analyzedAt="2026-10-06T08:00:00",
                model="glm-5.3",
            )
        moods = db.execute(select(models.Mood)).scalars().all()
        assert len(moods) == 1
        assert models.getMoodByEntry(db, entryId).summary == "睡了一觉好多了"


def test_moodCascadeDeleteWithEntry(dbFile):
    with database.getDb(dbFile) as db:
        entryId = models.addEntry(db, "带图的一天", "images/a.png", "2026-10-05T22:00:00")
        models.upsertMood(
                db,
                entryId=entryId,
                labels=["低落"],
                intensity=5,
                summary="",
                crisis=True,
                analyzedAt="2026-10-05T22:01:00",
                model="test",
            )
        entry = models.getEntry(db, entryId)
        db.delete(entry)
        db.flush()
        assert models.getMoodByEntry(db, entryId) is None


def test_messageRoundtripKeepsOrder(dbFile):
    with database.getDb(dbFile) as db:
        models.addMessage(db, "s1", "user", "在吗", "2026-10-05T21:00:00")
        models.addMessage(db, "s1", "assistant", "在的，今天怎么样？", "2026-10-05T21:00:05")
        models.addMessage(db, "s2", "user", "另一个会话", "2026-10-05T21:01:00")

        rows = models.listMessages(db, "s1")
        assert [m.role for m in rows] == ["user", "assistant"]


def test_settingsRoundtrip(dbFile):
    with database.getDb(dbFile) as db:
        assert models.getSetting(db, "base_url") is None
        models.setSetting(db, "base_url", "https://open.bigmodel.cn/api/paas/v4")
        models.setSetting(db, "base_url", "https://api.deepseek.com")
        assert models.getSetting(db, "base_url") == "https://api.deepseek.com"


def test_apiKeyEnvLoadAndMask(dataDir):
    assert config.getApiKey() == ""

    config.setApiKey("sk-1234567890abcdef")
    assert config.getApiKey() == "sk-1234567890abcdef"
    assert config.getEnvFile().exists()
    assert "DOWN_NOTE_API_KEY" in config.getEnvFile().read_text(encoding="utf-8")

    # 模拟重启：清掉进程内变量后从 .env 恢复
    os.environ.pop(config.API_KEY_ENV_NAME, None)
    config.loadEnv()
    assert config.getApiKey() == "sk-1234567890abcdef"

    assert config.maskApiKey("sk-1234567890abcdef") == "sk-***cdef"
    assert config.maskApiKey("short") == "*****"
    assert config.maskApiKey("") == ""
