"""日记条目接口：创建（文字/图片）、查询与心情记录读取。

图片存用户数据目录 images/，库中只存文件名；访问走 /api/images/{name}。
条目创建后触发后台分析（05），本模块自身不调模型；降级模式下照常可用。
对应开发文档：docx/v0.1.0/modules/04-记录模块.md、05-分析管线.md
"""

import asyncio
import json
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from down_note import config
from down_note.core import analysis
from down_note.core.events import ENTRY_EVENTS_CHANNEL, broker, sseFrame
from down_note.db import database, models

router = APIRouter(prefix="/api", tags=["entries"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class MoodRead(BaseModel):
    labels: list[str]
    intensity: int
    summary: str
    crisis: bool
    analyzedAt: str
    model: str


class ReplyRead(BaseModel):
    replyText: str
    createdAt: str
    sessionId: str | None
    transferred: bool


class EntryRead(BaseModel):
    id: int
    content: str
    imageUrl: str | None
    createdAt: str
    analyzed: bool
    analyzeState: str  # pending | running | failed | done
    kind: str = "entry"  # entry=当天条目 | daily=日整合日记
    mood: MoodRead | None
    reply: ReplyRead | None = None  # 条目回应（v0.3.0 01）；列表查询时装配


class EntryUpdateWrite(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


def _imagesDir() -> Path:
    return config.getImagesDir()


def _nowIso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def moodToRead(mood: models.Mood | None) -> MoodRead | None:
    if mood is None:
        return None
    return MoodRead(
            labels=json.loads(mood.labels),
            intensity=mood.intensity,
            summary=mood.summary,
            crisis=bool(mood.crisis),
            analyzedAt=mood.analyzed_at,
            model=mood.model,
        )


def replyToRead(reply: models.EntryReply | None) -> ReplyRead | None:
    if reply is None:
        return None
    return ReplyRead(
            replyText=reply.reply_text,
            createdAt=reply.created_at,
            sessionId=reply.session_id,
            transferred=reply.session_message_id is not None,
        )


def entryToRead(entry: models.Entry, reply: models.EntryReply | None = None) -> EntryRead:
    """ORM 条目 → 读模型（含心情记录与图片地址）；entry 需在会话内且 mood 可加载。

    reply 由调用方按需传入：列表与日页先用 getRepliesByEntries 批量取回再逐条装配，
    避免逐条查询（N+1）；单条响应不传，reply 即为 None。
    """
    return EntryRead(
            id=entry.id,
            content=entry.content,
            imageUrl=f"/api/images/{entry.image_path}" if entry.image_path else None,
            createdAt=entry.created_at,
            analyzed=bool(entry.analyzed),
            analyzeState=entry.analyze_state,
            kind=entry.kind,
            mood=moodToRead(entry.mood),
            reply=replyToRead(reply),
        )


def _validateImage(image: UploadFile) -> None:
    suffix = Path(image.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS or image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="只支持 jpg/png 图片")


def _saveImage(image: UploadFile) -> str:
    data = image.file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="图片超过 10MB 上限")
    if not data:
        raise HTTPException(status_code=400, detail="图片内容为空")
    suffix = Path(image.filename).suffix.lower()
    name = f"{uuid.uuid4().hex}{suffix}"
    imagesDir = _imagesDir()
    imagesDir.mkdir(parents=True, exist_ok=True)
    (imagesDir / name).write_bytes(data)
    return name


@router.post("/entries")
def createEntry(
        backgroundTasks: BackgroundTasks,
        content: str = Form(""),
        image: UploadFile | None = File(None),
    ) -> EntryRead:
    text = content.strip()
    hasImage = image is not None and bool(image.filename)
    if not text and not hasImage:
        raise HTTPException(status_code=400, detail="日记内容不能为空：至少要有文字或图片")

    imagePath: str | None = None
    if hasImage:
        _validateImage(image)
        imagePath = _saveImage(image)

    createdAt = _nowIso()
    with database.getDb() as db:
        entryId = models.addEntry(db, text, imagePath, createdAt)

    # 上传即析：响应返回后在后台线程执行；失败由兜底扫描收口
    backgroundTasks.add_task(analysis.analyzeEntry, entryId)
    return EntryRead(
            id=entryId,
            content=text,
            imageUrl=f"/api/images/{imagePath}" if imagePath else None,
            createdAt=createdAt,
            analyzed=False,
            analyzeState=models.ANALYZE_PENDING,
            kind="entry",
            mood=None,
        )


@router.get("/entries")
def listEntries(limit: int = 50, offset: int = 0) -> list[EntryRead]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 取值 1-200")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能为负")
    with database.getDb() as db:
        entries = models.listEntriesWithMood(db, limit=limit, offset=offset)
        replyMap = models.getRepliesByEntries(db, [entry.id for entry in entries])
        return [entryToRead(entry, replyMap.get(entry.id)) for entry in entries]


async def entryEventStream():
    """分析状态常驻事件流（独立生成器便于直接测试：TestClient 会缓冲完整响应，测不了无限流）。"""
    queue = broker.subscribe(ENTRY_EVENTS_CHANNEL)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield sseFrame(event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        broker.unsubscribe(ENTRY_EVENTS_CHANNEL, queue)


@router.get("/entries/events")
async def entryEvents() -> StreamingResponse:
    """分析状态通道：心情记录完成 / 失败即时推送（15 秒保活，与对话事件流同款）。"""
    return StreamingResponse(entryEventStream(), media_type="text/event-stream")


@router.put("/entries/{entryId}")
def updateEntry(
        entryId: int,
        body: EntryUpdateWrite,
        backgroundTasks: BackgroundTasks,
    ) -> EntryRead:
    """改今天写的条目：只允许"今天"（过去的日记一律锁定）。

    保存后清除旧的心情记录并后台重新分析（降级时留给兜底扫描）。
    """
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="内容不能为空")
    with database.getDb() as db:
        entry = models.getEntry(db, entryId)
        if entry is None:
            raise HTTPException(status_code=404, detail="条目不存在")
        if entry.created_at[:10] != date.today().isoformat():
            raise HTTPException(status_code=400, detail="过去的日记不能修改")
        models.updateEntryContent(db, entryId, text)
        models.clearMood(db, entryId)
        result = entryToRead(models.getEntry(db, entryId))
    backgroundTasks.add_task(analysis.analyzeEntry, entryId)
    return result


@router.post("/entries/{entryId}/reanalyze")
def reanalyzeEntry(entryId: int, backgroundTasks: BackgroundTasks) -> EntryRead:
    """重新分析一条日记（失败条目的「刷新」按钮）。

    状态处理：running 保持不动（避免与在跑的任务重复），其余回到 pending 再排一次后台分析；
    旧心情记录不清——新结果抵达前界面仍显示上一版，避免闪空。
    """
    with database.getDb() as db:
        entry = models.getEntry(db, entryId)
        if entry is None:
            raise HTTPException(status_code=404, detail="条目不存在")
        if entry.analyze_state != models.ANALYZE_RUNNING:
            models.setAnalyzeState(db, entryId, models.ANALYZE_PENDING)
        result = entryToRead(entry)
    backgroundTasks.add_task(analysis.analyzeEntry, entryId)
    return result


@router.get("/entries/{entryId}/mood")
def getEntryMood(entryId: int) -> MoodRead:
    with database.getDb() as db:
        mood = models.getMoodByEntry(db, entryId)
    if mood is None:
        raise HTTPException(status_code=404, detail="该条目还没有心情记录")
    return moodToRead(mood)


@router.post("/entries/{entryId}/reply/chat")
def chatAboutReply(entryId: int) -> ReplyRead:
    """「聊聊」：把回应原文零模型调用地追加进最近活跃会话；幂等。

    幂等分支校验目标会话仍存在——会话被物理删除后 session_message_id 不会清空，
    不校验会把用户带到已消失的空会话；会话没了就当作未转移、重新落库。
    """
    with database.getDb() as db:
        reply = models.getReplyByEntry(db, entryId)
        if reply is None:
            raise HTTPException(status_code=404, detail="该条目还没有回应")
        if (
                reply.session_message_id is not None
                and reply.session_id is not None
                and db.get(models.ChatSession, reply.session_id) is not None
            ):
            return replyToRead(reply)  # 已转移且会话仍在：直接回现状，不重复落库
        sessions = models.listRecentSessions(db, limit=1)
        sessionId = sessions[0].session_id if sessions else uuid.uuid4().hex
        createdAt = _nowIso()
        if not sessions:
            models.upsertChatSession(db, sessionId, createdAt)
        messageId = models.addMessage(db, sessionId, "assistant", reply.reply_text, createdAt)
        models.upsertChatSession(db, sessionId, createdAt)  # 刷新最近活跃
        models.markReplyTransferred(db, reply.id, sessionId, messageId)
        result = replyToRead(models.getReplyByEntry(db, entryId))
    broker.publish(sessionId, {"type": "message", "message": {
            "role": "assistant", "content": reply.reply_text, "createdAt": createdAt}})
    return result


@router.get("/images/{name}")
def getImage(name: str) -> FileResponse:
    # 防目录穿越：只接受纯文件名（".."、"..\\x"、"C:/x" 这类一律 404）
    if Path(name).name != name:
        raise HTTPException(status_code=404, detail="图片不存在")
    path = _imagesDir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path)
