"""时间域工具：getCurrentTime。

对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/00-结构重构.md
"""

from datetime import datetime

from langchain_core.tools import tool


@tool
def getCurrentTime() -> str:
    """获取当前的日期和时间。当需要知道"今天几号""现在几点"或需要时间上下文时调用。"""
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    now = datetime.now()
    return f"{now.strftime('%Y年%m月%d日 %H:%M')} {weekdays[now.weekday()]}"
