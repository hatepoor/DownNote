"""长期记忆工具：addMemory。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/01-记忆写入.md、
docx/v0.1.2/modules/10-记忆即时可见.md
"""

from langchain_core.tools import tool

from down_note.core.events import notifyMemoryChanged
from down_note.db import database, models


@tool
def addMemory(category: str, content: str) -> str:
    """新增一条长期记忆。category 二选一："basic"=身份与生活事实（姓名、性别、生日、家乡、居住地、学校、职业、家庭成员、正在做的事——如考研）；"psych"=性格画像（喜好与爱好、习惯、情绪模式、在意的事、应对方式）。判据：「喜欢 / 讨厌 / 习惯 / 在意」这类主观面一律 psych，只有姓名、地点、学校、生日、正在做的事才算 basic。content 是一句话事实，中文。用户明确让你"记一下 / 帮我记住"时直接调用；一时情绪与单次琐事不写（宁缺勿滥）。"""
    if category not in ("basic", "psych"):
        return "category 只能是 basic 或 psych"
    with database.getDb() as db:
        memoryId = models.addLongTermMemory(db, category, content, updatedBy="agent")
    notifyMemoryChanged()
    return f"已新增记忆 #{memoryId}：{content}"
