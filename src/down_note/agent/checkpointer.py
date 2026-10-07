"""LangGraph SQLite checkpointer：与业务同库、checkpointer 自管独立表。

职责边界（ADR-0005）：checkpointer 只做图状态恢复（多轮上下文延续），
不是短期记忆的载体——可展示、可回顾的对话存 messages 表。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from down_note import config

_saver: SqliteSaver | None = None


def getCheckpointer() -> SqliteSaver:
    global _saver
    if _saver is None:
        conn = sqlite3.connect(config.getDatabaseFile(), check_same_thread=False)
        _saver = SqliteSaver(conn)
    return _saver


def resetCheckpointer() -> None:
    global _saver
    _saver = None
