"""长期记忆工具包：增改删查，供记忆管理子智能体（07）与主智能体（08）绑定。

对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、docx/v0.1.2/modules/00-结构重构.md
"""

from down_note.agent.tools.memory.add import addMemory
from down_note.agent.tools.memory.delete import deleteMemory
from down_note.agent.tools.memory.list import listMemories
from down_note.agent.tools.memory.update import updateMemory

MEMORY_TOOLS = [listMemories, addMemory, updateMemory, deleteMemory]
