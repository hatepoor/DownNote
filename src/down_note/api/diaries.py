"""日记（按天）接口：历史天列表 + 某天的整合日记与当天原文。

整合日记是 kind="daily" 的 entries 行；心情记录与当天条目共用同一套分析产物。
对应开发文档：docx/v0.1.0/modules/11-日整合与交互修订.md
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from down_note.api.entries import EntryRead, MoodRead, entryToRead, moodToRead
from down_note.db import database, models

router = APIRouter(prefix="/api/diaries", tags=["diaries"])

PREVIEW_LENGTH = 80


class DiaryDayRead(BaseModel):
    day: str
    entryCount: int
    digested: bool
    preview: str
    mood: MoodRead | None


class DiaryDetailRead(BaseModel):
    day: str
    digest: EntryRead | None
    entries: list[EntryRead]


def _validDay(day: str) -> bool:
    return (
            len(day) == 10
            and day[4] == "-"
            and day[7] == "-"
            and day.replace("-", "").isdigit()
        )


@router.get("")
def listDiaries(limit: int = 20, offset: int = 0) -> list[DiaryDayRead]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 取值 1-100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能为负")
    with database.getDb() as db:
        dayCounts = models.listEntryDays(db, limit=limit, offset=offset)
        result = []
        for day, entryCount in dayCounts:
            digest = models.getDailyEntry(db, day)
            if digest is not None:
                mood = models.getMoodByEntry(db, digest.id)
                preview = digest.content[:PREVIEW_LENGTH]
            else:
                entries = models.listDayEntries(db, day)
                latest = entries[-1] if entries else None
                mood = models.getMoodByEntry(db, latest.id) if latest is not None else None
                preview = latest.content[:PREVIEW_LENGTH] if latest is not None else ""
            result.append(
                    DiaryDayRead(
                            day=day,
                            entryCount=entryCount,
                            digested=digest is not None,
                            preview=preview,
                            mood=moodToRead(mood),
                        )
                )
    return result


@router.get("/{day}")
def getDiaryDay(day: str) -> DiaryDetailRead:
    if not _validDay(day):
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    with database.getDb() as db:
        digest = models.getDailyEntry(db, day)
        entries = models.listDayEntries(db, day)
        return DiaryDetailRead(
                day=day,
                digest=entryToRead(digest) if digest is not None else None,
                entries=[entryToRead(entry) for entry in entries],
            )
