"""历史会话工具：getSessionMessages。

对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/00-结构重构.md
"""

from langchain_core.tools import tool

from down_note.agent.context import buildTranscript
from down_note.db import database, models


@tool
def getSessionMessages(sessionId: str) -> str:
    """读取某个历史会话的完整对话原文（编号来自 searchSessions）。"""
    with database.getDb() as db:
        messages = models.listMessages(db, sessionId, limit=200)
    if not messages:
        return "该会话不存在或没有消息。"
    return buildTranscript(messages)
