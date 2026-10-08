"""长期记忆工具：updateMemory。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md
"""

from langchain_core.tools import tool

from down_note.db import database, models


@tool
def updateMemory(memoryId: int, content: str) -> str:
    """修改一条长期记忆的内容（编号来自 listMemories）。用于信息变化或与现有记忆冲突时。"""
    with database.getDb() as db:
        ok = models.updateLongTermMemory(db, memoryId, content, updatedBy="agent")
    return f"已更新记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"
