"""会话生命周期：删除一次对话的全部痕迹收在一处。

长期记忆一律不动（用户口径："只删这次对话，仅此而已"）。
对应开发文档：docx/v0.2.0/modules/03-会话删除.md
"""

from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.context import forgetPromptBlocks
from down_note.db import database, models


def dropSession(sessionId: str) -> None:
    """物理删除会话的 checkpoint、消息、会话行与提示词快照；幂等。

    顺序：checkpoint 线程 → 消息 → 会话行 → 快照失效。
    先清图状态再清库行：图状态残留会让模型在删完后仍能复述这段对话；
    中途失败后重试，每一步都是幂等的。
    """
    getCheckpointer().delete_thread(sessionId)
    with database.getDb() as db:
        models.deleteSessionMessages(db, sessionId)
        models.deleteChatSession(db, sessionId)
    forgetPromptBlocks(sessionId)