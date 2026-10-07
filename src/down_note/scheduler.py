"""APScheduler 后台任务：日整合、兜底扫描未分析条目、日记记忆沉淀、会话记忆维护。

日整合：已结束的日子把当天条目纯程序拼接成一篇日记（kind="daily"），
随后由兜底扫描分析出"日心情"，再交记忆管理子智能体沉淀长期记忆。
对应开发文档：docx/v0.1.0/modules/05-分析管线.md、07-长期记忆.md、11-日整合与交互修订.md
"""

import logging
from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from down_note import config
from down_note.agent import memoryAgent
from down_note.agent.context import buildMemoriesText, buildMoodsText, buildTranscript, nowIso
from down_note.core import analysis
from down_note.db import database, models

SCAN_INTERVAL_MINUTES = 30
MAINTENANCE_INTERVAL_MINUTES = 30

_scheduler: BackgroundScheduler | None = None


def consolidatePastDays() -> None:
    """把已结束日子的当天条目整合成一篇日记（纯程序，不调模型）；幂等。"""
    today = date.today().isoformat()
    with database.getDb() as db:
        days = models.listPastDaysMissingDigest(db, today)
    for day in days:
        try:
            with database.getDb() as db:
                entries = models.listDayEntries(db, day)
                content = models.mergeDayBlocks(
                        [(entry.created_at, entry.content) for entry in entries if entry.content]
                    )
                if not content:
                    continue
                models.addDailyEntry(db, day, content)
            logging.getLogger(__name__).info("日整合完成：%s（%s 条）", day, len(entries))
        except Exception:
            logging.getLogger(__name__).exception("日期 %s 整合失败", day)


def scanUnanalyzed() -> None:
    """兜底：补扫所有未分析条目（即析失败、降级恢复后的收口；含整合日记）。"""
    with database.getDb() as db:
        entryIds = models.listUnanalyzedIds(db)
    for entryId in entryIds:
        try:
            analysis.analyzeEntry(entryId)
        except Exception:
            logging.getLogger(__name__).exception("条目 %s 分析失败", entryId)


def generateDiaryMemories() -> None:
    """已分析的整合日记 → 记忆管理子智能体（重复→不动 / 冲突→改 / 新增→记）。"""
    with database.getDb() as db:
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            return
        days = models.listDaysNeedingDiaryMemory(db)
    for day in days:
        try:
            with database.getDb() as db:
                digest = models.getDailyEntry(db, day)
                if digest is None:
                    continue
                mood = models.getMoodByEntry(db, digest.id)
                memoriesText = buildMemoriesText(models.listLongTermMemories(db))
                moodsText = buildMoodsText([(day, mood)]) if mood is not None else ""
                diaryText = digest.content
            memoryAgent.runDiaryMemory(cfg, diaryText, moodsText, memoriesText)
            with database.getDb() as db:
                models.setSetting(db, f"{models.DIARY_MEMORY_DONE_PREFIX}{day}", "1")
            logging.getLogger(__name__).info("日记记忆沉淀完成：%s", day)
        except Exception:
            logging.getLogger(__name__).exception("日期 %s 日记记忆沉淀失败", day)


def maintainMemories() -> None:
    """会后维护：对有新消息的会话跑记忆管理子智能体（降级时整体跳过）。"""
    now = nowIso()
    with database.getDb() as db:
        sessionIds = models.listSessionsNeedingMaintenance(db, now)
        if not sessionIds:
            return
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            return
        jobs = [
                (
                    sessionId,
                    buildTranscript(models.listMessages(db, sessionId)),
                    buildMemoriesText(models.listLongTermMemories(db)),
                    buildMoodsText(models.listRecentMoods(db, limit=20)),
                )
                for sessionId in sessionIds
            ]
    for sessionId, transcript, memoriesText, moodsText in jobs:
        try:
            memoryAgent.runMemoryMaintenance(cfg, transcript, memoriesText, moodsText)
            with database.getDb() as db:
                models.markSessionMaintained(db, sessionId, now)
        except Exception:
            logging.getLogger(__name__).exception("会话 %s 记忆维护失败", sessionId)


def scanAndConsolidate() -> None:
    """兜底主任务：日整合 → 未分析补扫 → 日记记忆沉淀（顺序保证先有日心情再沉淀）。"""
    consolidatePastDays()
    scanUnanalyzed()
    generateDiaryMemories()


def startScheduler() -> None:
    """启动兜底扫描与记忆维护调度器；重复调用幂等（lifespan 与测试环境多次创建应用）。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
            scanAndConsolidate,
            "interval",
            minutes=SCAN_INTERVAL_MINUTES,
            id="scan-and-consolidate",
        )
    _scheduler.add_job(
            maintainMemories,
            "interval",
            minutes=MAINTENANCE_INTERVAL_MINUTES,
            id="maintain-memories",
        )
    _scheduler.start()
