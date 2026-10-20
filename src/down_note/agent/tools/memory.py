"""长期记忆工具：增改删查，供记忆管理子智能体（07）与主智能体（08）绑定。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md、
docx/v0.1.2/modules/10-记忆即时可见.md
"""

from langchain_core.tools import tool

from down_note.core.events import notifyMemoryChanged
from down_note.db import database, models


@tool
def listMemories() -> str:
    """读取当前全部长期记忆，返回每条的编号、类别、内容与记录日期。修改或删除前必须先调用以获取编号；用户说"哪天记的那条"时按返回里的日期定位到编号再操作。"""
    with database.getDb() as db:
        memories = models.listLongTermMemories(db)
    if not memories:
        return "（当前没有任何长期记忆）"
    categoryName = {"basic": "基本信息", "psych": "性格画像"}
    return "\n".join(
            f"#{m.id} [{categoryName[m.category]}] {m.content} （记于 {m.created_at[:10]}）"
            for m in memories
        )


@tool
def addMemory(category: str, content: str) -> str:
    """新增一条长期记忆。category 二选一："basic"=身份与生活事实（姓名、性别、生日、家乡、居住地、学校、职业、家庭成员、正在做的事——如考研）；"psych"=性格画像（喜好与爱好、习惯、情绪模式、在意的事、应对方式）。判据：「喜欢 / 讨厌 / 习惯 / 在意」这类主观面一律 psych，只有姓名、地点、学校、生日、正在做的事才算 basic。content 是一句话事实，中文。用户明确让你"记一下 / 帮我记住"时直接调用；一时情绪与单次琐事不写（宁缺勿滥）。"""
    if category not in ("basic", "psych"):
        return "category 只能是 basic 或 psych"
    with database.getDb() as db:
        memoryId = models.addLongTermMemory(db, category, content, updatedBy="agent")
    notifyMemoryChanged()
    return f"已新增记忆 #{memoryId}：{content}"


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


@tool
def deleteMemory(memoryId: int) -> str:
    """删除一条过时或错误的长期记忆（编号来自 listMemories）。仅在明确过时、错误或用户要求时使用。"""
    with database.getDb() as db:
        ok = models.deleteLongTermMemory(db, memoryId)
    if ok:
        notifyMemoryChanged()
    return f"已删除记忆 #{memoryId}" if ok else f"记忆 #{memoryId} 不存在"


MEMORY_TOOLS = [listMemories, addMemory, updateMemory, deleteMemory]
