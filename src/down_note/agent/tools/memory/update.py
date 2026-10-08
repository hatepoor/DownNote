"""长期记忆工具：updateMemory。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.1.2/modules/10-记忆即时可见.md
"""

from langchain_core.tools import tool

from down_note.core.events import notifyMemoryChanged
from down_note.db import database, models


@tool
def updateMemory(memoryId: int, content: str, category: str | None = None) -> str:
    """修改一条长期记忆的内容（编号来自 listMemories）。用于信息变化或与现有记忆冲突时。category 可选，给了就一并改分类，只能是 "basic"（身份与生活事实：姓名、生日、家乡、学校、职业、正在做的事）或 "psych"（性格画像：喜好与爱好、习惯、情绪模式、在意的事）——发现这条记忆的类别明显放错时（如把"喜欢看漫画"记成 basic）才给。"""
    if category is not None and category not in ("basic", "psych"):
        return "category 只能是 basic 或 psych"
    with database.getDb() as db:
        ok = models.updateLongTermMemory(
                db,
                memoryId,
                content,
                updatedBy="agent",
                category=category,
            )
    if ok:
        notifyMemoryChanged()
    return f"已更新记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"
