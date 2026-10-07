"""长期记忆与会话表测试：ORM 往返与维护触发判定。

对应模块：docx/v0.1.0/modules/07-长期记忆.md
"""

from down_note.db import database, models


def test_memoryCrudRoundtrip(dbFile):
    with database.getDb(dbFile) as db:
        memoryId = models.addLongTermMemory(db, "basic", "用户叫林晓", updatedBy="agent")
        assert memoryId == 1

        memories = models.listLongTermMemories(db)
        assert len(memories) == 1
        assert memories[0].content == "用户叫林晓"
        assert memories[0].created_at == memories[0].updated_at
        assert memories[0].updated_by == "agent"

        assert models.updateLongTermMemory(db, memoryId, "用户叫林夏", updatedBy="agent") is True
        updated = models.listLongTermMemories(db)[0]
        assert updated.content == "用户叫林夏"
        assert updated.updated_at >= updated.created_at

        assert models.deleteLongTermMemory(db, memoryId) is True
        assert models.listLongTermMemories(db) == []
        assert models.deleteLongTermMemory(db, memoryId) is False


def test_sessionMaintenanceStates(dbFile):
    with database.getDb(dbFile) as db:
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")
        # 从未维护 → 需要维护
        assert models.listSessionsNeedingMaintenance(db, "2026-10-05T21:30:00") == ["s1"]

        models.markSessionMaintained(db, "s1", "2026-10-05T21:30:00")
        # 维护后无新消息 → 不需要
        assert models.listSessionsNeedingMaintenance(db, "2026-10-05T22:00:00") == []

        # 又有新消息（活跃晚于维护时间）→ 需要
        models.upsertChatSession(db, "s1", "2026-10-05T22:10:00")
        assert models.listSessionsNeedingMaintenance(db, "2026-10-05T22:20:00") == ["s1"]


def test_upsertChatSessionKeepsStartedAt(dbFile):
    with database.getDb(dbFile) as db:
        models.upsertChatSession(db, "s1", "2026-10-05T21:00:00")
        models.upsertChatSession(db, "s1", "2026-10-05T21:05:00")
        session = db.get(models.ChatSession, "s1")
        assert session.started_at == "2026-10-05T21:00:00"
        assert session.last_active_at == "2026-10-05T21:05:00"


def test_listRecentMoodsJoinedWithEntryTime(dbFile):
    with database.getDb(dbFile) as db:
        entryId = models.addEntry(db, "有点低落", None, "2026-10-05T21:00:00")
        models.upsertMood(
                db,
                entryId=entryId,
                labels=["低落"],
                intensity=5,
                summary="测试",
                crisis=False,
                analyzedAt="2026-10-05T21:05:00",
                model="test",
            )
        pairs = models.listRecentMoods(db, limit=20)
        assert len(pairs) == 1
        createdAt, mood = pairs[0]
        assert createdAt == "2026-10-05T21:00:00"
        assert mood.intensity == 5
