"""长期记忆工具：listMemories。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md
"""

from langchain_core.tools import tool

from down_note.db import database, models


@tool
def listMemories() -> str:
    """读取当前全部长期记忆，返回每条的编号、类别与内容。修改或删除前必须先调用以获取编号。"""
    with database.getDb() as db:
        memories = models.listLongTermMemories(db)
    if not memories:
        return "（当前没有任何长期记忆）"
    categoryName = {"basic": "基本信息", "psych": "性格画像"}
    return "\n".join(f"#{m.id} [{categoryName[m.category]}] {m.content}" for m in memories)
