"""历史会话工具：检索会话与读取原文，供回顾子智能体（08）绑定。

对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/00-结构重构.md
"""

from langchain_core.tools import tool

from down_note.agent.context import buildTranscript
from down_note.db import database, models


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
