"""智能体工具集：获取时间、日记查询、长期记忆增改删查。

工具自身开短会话读写库（与全项目短会话策略一致，无跨工具事务）；
供记忆管理子智能体（07）与主智能体（08）绑定。
对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、08-对话Agent.md、12-体验修订.md
"""

from datetime import datetime

from langchain_core.tools import tool

from down_note.agent.context import buildTranscript
from down_note.db import database, models


def _nowIso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@tool
def getCurrentTime() -> str:
    """获取当前的日期和时间。当需要知道"今天几号""现在几点"或需要时间上下文时调用。"""
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    now = datetime.now()
    return f"{now.strftime('%Y年%m月%d日 %H:%M')} {weekdays[now.weekday()]}"


def _validDay(day: str) -> bool:
    return (
            len(day) == 10
            and day[4] == "-"
            and day[7] == "-"
            and day.replace("-", "").isdigit()
        )


def _formatDiaryLine(entry) -> str:
    day = entry.created_at[:10]
    if entry.kind == "daily":
        return f"{day} 整合日记：{entry.content[:400]}"
    return f"{day} {entry.created_at[11:16]} 日记：{entry.content[:300]}"


@tool
def queryDiaries(date: str = "", keyword: str = "") -> str:
    """查询用户写过的日记原文。date 传 YYYY-MM-DD（"昨天"这类说法先用 getCurrentTime 换算成具体日期再查）；keyword 传要搜索的词。两者都给则取交集；都不给返回最近的日记。"""
    date = date.strip()
    keyword = keyword.strip()
    if date and not _validDay(date):
        return "日期格式应为 YYYY-MM-DD，例如 2026-10-05；请先用 getCurrentTime 换算。"
    with database.getDb() as db:
        if date:
            digest = models.getDailyEntry(db, date)
            entries = models.listDayEntries(db, date)
            if keyword:
                entries = [entry for entry in entries if keyword in entry.content]
                if digest is not None and keyword not in digest.content:
                    digest = None
            lines = []
            if digest is not None:
                lines.append(_formatDiaryLine(digest))
            lines.extend(_formatDiaryLine(entry) for entry in entries)
        elif keyword:
            lines = [
                    _formatDiaryLine(entry)
                    for entry in models.searchEntries(db, keyword, limit=10)
                ]
        else:
            lines = [
                    _formatDiaryLine(entry)
                    for entry in models.listEntriesWithMood(db, limit=5, offset=0)
                ]
    if not lines:
        if date and keyword:
            return f"{date} 这一天没有包含“{keyword}”的日记。"
        if date:
            return f"{date} 这一天没有日记。"
        if keyword:
            return f"没有查到包含“{keyword}”的日记。"
        return "（还没有日记）"
    return "\n\n".join(lines)


@tool
def listMemories() -> str:
    """读取当前全部长期记忆，返回每条的编号、类别与内容。修改或删除前必须先调用以获取编号。"""
    with database.getDb() as db:
        memories = models.listLongTermMemories(db)
    if not memories:
        return "（当前没有任何长期记忆）"
    categoryName = {"basic": "基本信息", "psych": "性格画像"}
    return "\n".join(f"#{m.id} [{categoryName[m.category]}] {m.content}" for m in memories)


@tool
def addMemory(category: str, content: str) -> str:
    """新增一条长期记忆。category 只能是 "basic"（姓名、性别、生日、生活状态等基本信息）或 "psych"（情绪模式、在意的事、应对方式等性格画像）。content 是一句话事实，中文。"""
    if category not in ("basic", "psych"):
        return "category 只能是 basic 或 psych"
    with database.getDb() as db:
        memoryId = models.addLongTermMemory(db, category, content, updatedBy="agent")
    return f"已新增记忆 #{memoryId}：{content}"


@tool
def updateMemory(memoryId: int, content: str) -> str:
    """修改一条长期记忆的内容（编号来自 listMemories）。用于信息变化或与现有记忆冲突时。"""
    with database.getDb() as db:
        ok = models.updateLongTermMemory(db, memoryId, content, updatedBy="agent")
    return f"已更新记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"


@tool
def deleteMemory(memoryId: int) -> str:
    """删除一条过时或错误的长期记忆（编号来自 listMemories）。仅在明确过时、错误或用户要求时使用。"""
    with database.getDb() as db:
        ok = models.deleteLongTermMemory(db, memoryId)
    return f"已删除记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"


MEMORY_TOOLS = [listMemories, addMemory, updateMemory, deleteMemory]


@tool
def searchSessions() -> str:
    """列出最近的历史对话会话（编号与开始时间）。回忆往事前先用它看可查范围。"""
    with database.getDb() as db:
        sessions = models.listRecentSessions(db, limit=10)
    if not sessions:
        return "（还没有历史会话）"
    return "\n".join(f"#{s.session_id} 开始于 {s.started_at}" for s in sessions)


@tool
def getSessionMessages(sessionId: str) -> str:
    """读取某个历史会话的完整对话原文（编号来自 searchSessions）。"""
    with database.getDb() as db:
        messages = models.listMessages(db, sessionId, limit=200)
    if not messages:
        return "该会话不存在或没有消息。"
    return buildTranscript(messages)


RECALL_TOOLS = [searchSessions, getSessionMessages]
