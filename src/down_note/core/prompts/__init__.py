"""分析与危机提示词包：一用途一文件，汇总导出保持旧调用路径不变。

常量以用途命名（如 ANALYZE_MOOD_PROMPT），不使用泛化的 "PROMPT" 命名。
智能体提示词在 agent/prompts/。使用方：05-分析管线、06-危机应对。
对应开发文档：docx/v0.1.2/modules/00-结构重构.md
"""

from down_note.core.prompts.analyzeMood import ANALYZE_MOOD_PROMPT
from down_note.core.prompts.crisis import CRISIS_ASSESS_PROMPT, CRISIS_RESPONSE_GUIDELINES
