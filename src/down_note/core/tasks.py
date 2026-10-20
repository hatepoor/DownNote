"""后台任务实现：日整合、未分析补扫、日记记忆沉淀、会话记忆维护、启动恢复。

scheduler 只做注册，不持有任务实现；分析 → 回应的编排在 core/pipeline。
对应开发文档：docx/v0.1.0/modules/05-分析管线.md、07-长期记忆.md、11-日整合与交互修订.md、
docx/v0.1.2/modules/02-分析提速.md、docx/v0.1.2/modules/12-日整合即时补跑.md
"""

import logging
from datetime import date

from down_note import config
from down_note.agent import memoryAgent
from down_note.agent.context import buildMemoriesText, buildMoodsText, buildTranscript, nowIso
from down_note.core import pipeline
from down_note.core.events import ENTRY_EVENTS_CHANNEL, broker
from down_note.db import database, models

logger = logging.getLogger(__name__)


def consolidatePastDays() -> None:
    """把已结束日子的当天条目整合成一篇日记（纯程序，不调模型）；幂等。

    新建整合日记后推一条事件：正开着那一天的日页会即时刷新出"这一天的心情"与分析状态。
    """
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
                digestId = models.addDailyEntry(db, day, content)
            broker.publish(
                    ENTRY_EVENTS_CHANNEL,
                    {"type": "digest", "entryId": digestId, "analyzeState": models.ANALYZE_PENDING},
                )
            logger.info("日整合完成：%s（%s 条）", day, len(entries))
        except Exception:
            logger.exception("日期 %s 整合失败", day)


def scanUnanalyzed() -> None:
    """兜底：补扫所有未分析条目（即析失败、降级恢复后的收口；含整合日记）。"""
    with database.getDb() as db:
        entryIds = models.listUnanalyzedIds(db)
    for entryId in entryIds:
        try:
            pipeline.analyzeAndReply(entryId)
        except Exception:
            logger.exception("条目 %s 分析失败", entryId)


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
            logger.info("日记记忆沉淀完成：%s", day)
        except Exception:
            logger.exception("日期 %s 日记记忆沉淀失败", day)


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
            logger.exception("会话 %s 记忆维护失败", sessionId)


def recoverInterruptedAnalyses() -> None:
    """启动恢复：把上次运行遗留的 running 条目置回 pending（应用被关掉时任务中断）。

    只在启动时执行——运行期间不重置，避免误伤进行中的分析、破坏认领互斥。
    """
    with database.getDb() as db:
        count = models.resetStaleRunning(db)
    if count:
        logger.info("恢复 %s 条中断的分析任务", count)


def scanAndConsolidate() -> None:
    """兜底主任务：日整合 → 未分析补扫 → 日记记忆沉淀（顺序保证先有日心情再沉淀）。"""
    consolidatePastDays()
    scanUnanalyzed()
    generateDiaryMemories()