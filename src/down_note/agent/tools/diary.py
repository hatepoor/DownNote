"""日记查询工具：queryDiaries（含日期校验与行格式化私有辅助）。

对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/00-结构重构.md
"""

from langchain_core.tools import tool

from down_note.db import database, models


def _validDay(day: str) -> bool:
    return (
            len(day) == 10
            and day[4] == "-"
            and day[7] == "-"
            and day.replace("-", "").isdigit()
        )


def _formatDiaryLine(entry) -> str:
    day = entry.created_at[:10]
    if entry.kind == "daily":
        return f"{day} 整合日记：{entry.content[:400]}"
    return f"{day} {entry.created_at[11:16]} 日记：{entry.content[:300]}"


@tool
def queryDiaries(date: str = "", keyword: str = "") -> str:
    """查询用户写过的日记原文。date 传 YYYY-MM-DD（"昨天"这类说法先用 getCurrentTime 换算成具体日期再查）；keyword 传要搜索的词。两者都给则取交集；都不给返回最近的日记。"""
    date = date.strip()
    keyword = keyword.strip()
    if date and not _validDay(date):
        return "日期格式应为 YYYY-MM-DD，例如 2026-10-05；请先用 getCurrentTime 换算。"
    with database.getDb() as db:
        if date:
            digest = models.getDailyEntry(db, date)
            entries = models.listDayEntries(db, date)
            if keyword:
                entries = [entry for entry in entries if keyword in entry.content]
                if digest is not None and keyword not in digest.content:
                    digest = None
            lines = []
            if digest is not None:
                lines.append(_formatDiaryLine(digest))
            lines.extend(_formatDiaryLine(entry) for entry in entries)
        elif keyword:
            lines = [
                    _formatDiaryLine(entry)
                    for entry in models.searchEntries(db, keyword, limit=10)
                ]
        else:
            lines = [
                    _formatDiaryLine(entry)
                    for entry in models.listEntriesWithMood(db, limit=5, offset=0)
                ]
    if not lines:
        if date and keyword:
            return f"{date} 这一天没有包含“{keyword}”的日记。"
        if date:
            return f"{date} 这一天没有日记。"
        if keyword:
            return f"没有查到包含“{keyword}”的日记。"
        return "（还没有日记）"
    return "\n\n".join(lines)
