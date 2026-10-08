"""智能体提示词包：一角色场景一文件，汇总导出保持旧调用路径不变。

常量以用途命名；话术资产，禁止散落在业务代码中。
对应开发文档：docx/v0.1.0/modules/07-长期记忆.md、08-对话Agent.md、docx/v0.1.2/modules/00-结构重构.md
"""

from down_note.agent.prompts.companion import COMPANION_SYSTEM_PROMPT, WAKE_INSTRUCTION
from down_note.agent.prompts.diaryMemory import DIARY_MEMORY_PROMPT
from down_note.agent.prompts.memoryMaintenance import MEMORY_MAINTENANCE_PROMPT
from down_note.agent.prompts.recall import RECALL_PROMPT
