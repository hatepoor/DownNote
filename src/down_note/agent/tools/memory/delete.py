"""长期记忆工具：deleteMemory。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.1.2/modules/10-记忆即时可见.md
"""

from langchain_core.tools import tool

from down_note.core.events import notifyMemoryChanged
from down_note.db import database, models


@tool
def deleteMemory(memoryId: int) -> str:
    """删除一条过时或错误的长期记忆（编号来自 listMemories）。仅在明确过时、错误或用户要求时使用。"""
    with database.getDb() as db:
        ok = models.deleteLongTermMemory(db, memoryId)
    if ok:
        notifyMemoryChanged()
    return f"已删除记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"
