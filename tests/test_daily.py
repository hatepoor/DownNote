"""日整合与日记记忆沉淀测试：kind 迁移、整合幂等、日心情、记忆沉淀标记、按天接口。

对应模块：docx/v0.1.0/modules/11-日整合与交互修订.md
"""

import json
import sqlite3
from datetime import date

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select

from helpers import FakeToolModel, toolCall

from down_note import scheduler
from down_note.agent import llm as agentLlm
from down_note.agent import memoryAgent
from down_note.agent.tools import queryDiaries
from down_note.app import createApp
from down_note.db import database, models

TODAY = date.today().isoformat()


def _configure(db) -> None:
    models.setSetting(db, "base_url", "http://model.local/v1")
    models.setSetting(db, "model_name", "test-model")


def test_migrationAddsKindColumn(tmp_path):
    """旧 v2 库（无 kind 列）经 ensureSchema 后补列并回填 'entry'。"""
    database.resetEngine()
    dbPath = tmp_path / "old.db"
    conn = sqlite3.connect(dbPath)
    conn.execute(
            "CREATE TABLE entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, image_path VARCHAR, "
            "created_at VARCHAR NOT NULL, analyzed BOOLEAN NOT NULL)"
        )
    conn.execute(
            "INSERT INTO entries (content, created_at, analyzed) "
            "VALUES ('旧条目', '2026-10-05T21:00:00', 1)"
        )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    database.ensureSchema(dbPath)

    conn = sqlite3.connect(dbPath)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    assert "kind" in columns
    assert conn.execute("SELECT content, kind FROM entries").fetchone() == ("旧条目", "entry")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    conn.close()
    database.resetEngine()


def test_migrationRemergesDailyDigestsAsPlainText(tmp_path):
    """旧库的旧格式整合日记迁移后按当天原始条目重拼为纯文本（时间戳/分隔线均已废弃）：
    心情不进正文，由日页按条展示。"""
    database.resetEngine()
    dbPath = tmp_path / "v3.db"
    conn = sqlite3.connect(dbPath)
    conn.execute(
            "CREATE TABLE entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, image_path VARCHAR, "
            "created_at VARCHAR NOT NULL, analyzed BOOLEAN NOT NULL, kind VARCHAR NOT NULL)"
        )
    conn.execute(
            "INSERT INTO entries (content, created_at, analyzed, kind) "
            "VALUES ('早上很累。', '2026-10-05T09:00:00', 1, 'entry')"
        )
    conn.execute(
            "INSERT INTO entries (content, created_at, analyzed, kind) "
            "VALUES ('晚上好些了。\n\n还做了个梦。', '2026-10-05T21:00:00', 1, 'entry')"
        )
    conn.execute(
            "INSERT INTO entries (content, created_at, analyzed, kind) "
            "VALUES ('早上很累。\n\n晚上好些了。\n\n还做了个梦。', '2026-10-05T23:59:59', 1, 'daily')"
        )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    database.ensureSchema(dbPath)

    conn = sqlite3.connect(dbPath)
    digest = conn.execute("SELECT content FROM entries WHERE kind = 'daily'").fetchone()[0]
    assert digest == "早上很累。\n\n晚上好些了。\n\n还做了个梦。"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    conn.close()
    database.resetEngine()


def test_consolidateMergesPastDayAndIsIdempotent(dbFile):
    with database.getDb() as db:
        models.addEntry(db, "早上很累。", None, "2026-10-05T09:00:00")
        models.addEntry(db, "晚上好些了。", None, "2026-10-05T21:00:00")
        models.addEntry(db, "今天写的。", None, f"{TODAY}T10:00:00")

    scheduler.consolidatePastDays()

    with database.getDb() as db:
        digest = models.getDailyEntry(db, "2026-10-05")
        assert digest is not None
        assert digest.kind == "daily"
        # 整合正文保持纯文本；条目各自的心情由日页按条展示
        assert digest.content == "早上很累。\n\n晚上好些了。"
        assert digest.created_at == "2026-10-05T23:59:59"
        # 今天不整合
        assert models.getDailyEntry(db, TODAY) is None
        assert models.listPastDaysMissingDigest(db, TODAY) == []

    # 幂等：二跑不再新增
    scheduler.consolidatePastDays()
    with database.getDb() as db:
        dailies = db.execute(
                select(models.Entry).where(models.Entry.kind == "daily")
            ).scalars().all()
        assert len(dailies) == 1


def test_scanAndConsolidateAnalyzesDigestThenFeedsMemory(dbFile, monkeypatch):
    """整合 → 兜底扫描出日心情 → 记忆沉淀 + 标记；二跑不重复也不重复沉淀。"""
    with database.getDb() as db:
        _configure(db)
        models.addEntry(db, "今天走了很远的路，心里松了一点。", None, "2026-10-05T21:00:00")

    moodJson = json.dumps(
            {"labels": ["平静"], "intensity": 4, "summary": "走了很远，松了一点"},
            ensure_ascii=False,
        )
    monkeypatch.setattr(
            agentLlm,
            "buildChatModel",
            lambda cfg, **kw: FakeToolModel(messages=iter([AIMessage(content=moodJson)])),
        )
    ran = []

    def _fakeDiaryMemory(cfg, diaryText, moodsText, memoriesText):
        ran.append((diaryText, moodsText))
        return "无需更新"

    monkeypatch.setattr(memoryAgent, "runDiaryMemory", _fakeDiaryMemory)

    scheduler.scanAndConsolidate()

    with database.getDb() as db:
        digest = models.getDailyEntry(db, "2026-10-05")
        assert digest is not None and bool(digest.analyzed)
        mood = models.getMoodByEntry(db, digest.id)
        assert mood is not None and mood.intensity == 4
        assert db.get(models.Setting, f"{models.DIARY_MEMORY_DONE_PREFIX}2026-10-05") is not None
    assert len(ran) == 1
    assert "走了很远" in ran[0][0]
    assert "2026-10-05" in ran[0][1]

    # 二跑：没有新工作，不再触发沉淀
    scheduler.scanAndConsolidate()
    assert len(ran) == 1


def test_diaryMemorySkippedWhenNotConfigured(dbFile, monkeypatch):
    with database.getDb() as db:
        models.addEntry(db, "一句话。", None, "2026-10-05T21:00:00")
    scheduler.consolidatePastDays()
    with database.getDb() as db:
        digest = models.getDailyEntry(db, "2026-10-05")
        models.markEntryAnalyzed(db, digest.id)

    ran = []
    monkeypatch.setattr(
            memoryAgent,
            "runDiaryMemory",
            lambda cfg, diaryText, moodsText, memoriesText: ran.append(diaryText) or "x",
        )
    scheduler.generateDiaryMemories()  # 未配置模型 → 整体跳过，且不落标记

    assert ran == []
    with database.getDb() as db:
        assert db.get(models.Setting, f"{models.DIARY_MEMORY_DONE_PREFIX}2026-10-05") is None


def test_diaryMemoryRunsRealGraphWithToolCall(dbFile, monkeypatch):
    """真实记忆子智能体图：日记里的名字经 addMemory 工具落库。"""
    with database.getDb() as db:
        _configure(db)
        models.addEntry(db, "医生说，林晓这个名字挺好听的。", None, "2026-10-05T21:00:00")
    scheduler.consolidatePastDays()
    with database.getDb() as db:
        digest = models.getDailyEntry(db, "2026-10-05")
        models.markEntryAnalyzed(db, digest.id)

    model = FakeToolModel(
            messages=iter([
                toolCall("addMemory", {"category": "basic", "content": "用户叫林晓"}, "call-1"),
                AIMessage(content="新增了一条基本信息。"),
            ])
        )
    monkeypatch.setattr(agentLlm, "buildChatModel", lambda cfg, **kw: model)

    scheduler.generateDiaryMemories()

    with database.getDb() as db:
        memories = models.listLongTermMemories(db)
        assert len(memories) == 1
        assert memories[0].content == "用户叫林晓"
        assert db.get(models.Setting, f"{models.DIARY_MEMORY_DONE_PREFIX}2026-10-05") is not None


def test_diariesApiListsDaysAndDetail(dbFile):
    with database.getDb() as db:
        firstId = models.addEntry(db, "昨天写的第一条", None, "2026-10-05T21:00:00")
        models.upsertMood(
                db,
                entryId=firstId,
                labels=["平静"],
                intensity=4,
                summary="还行",
                crisis=False,
                analyzedAt="2026-10-05T21:05:00",
                model="test",
            )
        models.addEntry(db, "昨天写的第二条", None, "2026-10-05T22:00:00")
        models.addDailyEntry(db, "2026-10-05", "昨天写的第一条\n\n昨天写的第二条")
        models.addEntry(db, "今天写的", None, f"{TODAY}T10:00:00")

    client = TestClient(createApp())
    days = client.get("/api/diaries").json()
    assert [item["day"] for item in days] == [TODAY, "2026-10-05"]
    assert days[0]["digested"] is False
    assert days[0]["entryCount"] == 1
    assert days[1]["digested"] is True
    assert days[1]["entryCount"] == 2
    assert days[1]["preview"].startswith("昨天写的第一条")

    detail = client.get("/api/diaries/2026-10-05").json()
    assert detail["digest"]["kind"] == "daily"
    assert [entry["content"] for entry in detail["entries"]] == ["昨天写的第一条", "昨天写的第二条"]
    assert detail["entries"][0]["mood"]["intensity"] == 4

    todayDetail = client.get(f"/api/diaries/{TODAY}").json()
    assert todayDetail["digest"] is None
    assert len(todayDetail["entries"]) == 1

    assert client.get("/api/diaries/2026-1-5").status_code == 400
    assert client.get("/api/diaries?limit=0").status_code == 400


def test_queryDiariesByDateAndKeyword(dbFile):
    """⑤ 日记查询工具：按日期/关键词命中与未命中，不串天。"""
    with database.getDb() as db:
        models.addEntry(db, "今天试用了刚写好的记录页。", None, "2026-10-05T21:08:00")
        models.addEntry(db, "今天把分析管线接好了。", None, "2026-10-05T21:28:00")
        models.addDailyEntry(db, "2026-10-05", "今天试用了刚写好的记录页。\n\n今天把分析管线接好了。")
        models.addEntry(db, "今天风很大。", None, "2026-10-06T10:00:00")

    byDate = queryDiaries.invoke({"date": "2026-10-05"})
    assert "整合日记" in byDate
    assert "21:08" in byDate and "分析管线" in byDate
    assert "风很大" not in byDate  # 不串到别的天

    assert "这一天没有日记" in queryDiaries.invoke({"date": "2026-01-01"})
    assert "格式应为" in queryDiaries.invoke({"date": "10-05"})

    byKeyword = queryDiaries.invoke({"keyword": "分析管线"})
    assert "2026-10-05" in byKeyword and "分析管线" in byKeyword
    assert "风很大" not in byKeyword
    assert "没有查到" in queryDiaries.invoke({"keyword": "不存在的词"})

    # 日期 + 关键词取交集（该天没有含此词的内容）
    both = queryDiaries.invoke({"date": "2026-10-05", "keyword": "风很大"})
    assert "没有包含" in both
