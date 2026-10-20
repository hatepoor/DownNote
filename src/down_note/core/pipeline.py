"""条目处理编排：分析成功 → 当天条目生成回应。

分析与回应生成各自是独立 module；这里只表达两者之间的因果顺序，
让「分析完成之后会发生什么」在一个函数体里可见。
对应开发文档：docx/v0.3.0/modules/01-日记回应.md
"""

import logging

from down_note.core import analysis, entryReply

logger = logging.getLogger(__name__)


def analyzeAndReply(entryId: int) -> analysis.MoodResult | None:
    """分析一条日记；成功产出后尝试生成条目回应（回应失败不影响分析结果）。"""
    result = analysis.analyzeEntry(entryId)
    if result is None:
        return None
    try:
        entryReply.generateEntryReply(entryId)
    except Exception:
        logger.exception("条目回应步骤异常（条目 %s）", entryId)
    return result