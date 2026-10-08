"""长期记忆接口：给用户（人）的查看 / 新增 / 编辑 / 删除通道。

智能体侧走 agent/tools.py，两侧共用同一张表与 models.py 的访问函数：
用户编辑与智能体维护同等有效，不设修改锁（CONTEXT.md「长期记忆」）。
这里落库的 updated_by 固定为 "user"，供前端区分"你写的 / 它记下的"。
变更推送：任何写入成功后经 MEMORY_EVENTS_CHANNEL 通知前端刷新（见 10-记忆即时可见）。
对应开发文档：docx/v0.1.0/modules/09-整合与降级.md、docx/v0.1.2/modules/10-记忆即时可见.md
"""

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from down_note.core.events import MEMORY_EVENTS_CHANNEL, broker, notifyMemoryChanged, sseFrame
from down_note.db import database, models

router = APIRouter(prefix="/api/memories", tags=["memories"])

CATEGORIES = ("basic", "psych")
CONTENT_MAX_LENGTH = 500


class MemoryRead(BaseModel):
    id: int
    category: str
    content: str
    updatedBy: str
    createdAt: str
    updatedAt: str


class MemoryWrite(BaseModel):
    content: str = Field(min_length=1, max_length=CONTENT_MAX_LENGTH)
    category: str = "basic"  # 仅新增时使用；编辑只认 content


def _cleanContent(raw: str) -> str:
    content = raw.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")
    return content


def _toRead(memory: models.LongTermMemory) -> MemoryRead:
    return MemoryRead(
            id=memory.id,
            category=memory.category,
            content=memory.content,
            updatedBy=memory.updated_by,
            createdAt=memory.created_at,
            updatedAt=memory.updated_at,
        )


@router.get("")
def listMemories() -> list[MemoryRead]:
    with database.getDb() as db:
        return [_toRead(memory) for memory in models.listLongTermMemories(db)]


async def memoryEventStream():
    """长期记忆常驻事件流（独立生成器便于直接测试：TestClient 会缓冲完整响应，测不了无限流）。"""
    queue = broker.subscribe(MEMORY_EVENTS_CHANNEL)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield sseFrame(event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        broker.unsubscribe(MEMORY_EVENTS_CHANNEL, queue)


@router.get("/events")
async def memoryEvents() -> StreamingResponse:
    """记忆变更通道：任何写入（智能体 / 用户）成功后即时推送（15 秒保活，与分析状态流同款）。"""
    return StreamingResponse(memoryEventStream(), media_type="text/event-stream")


@router.post("", status_code=201)
def createMemory(body: MemoryWrite) -> MemoryRead:
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="category 只能是 basic 或 psych")
    with database.getDb() as db:
        memoryId = models.addLongTermMemory(
                db,
                body.category,
                _cleanContent(body.content),
                updatedBy="user",
            )
        memory = _toRead(models.getLongTermMemory(db, memoryId))
    notifyMemoryChanged()
    return memory


@router.put("/{memoryId}")
def updateMemory(memoryId: int, body: MemoryWrite) -> MemoryRead:
    with database.getDb() as db:
        ok = models.updateLongTermMemory(
                db,
                memoryId,
                _cleanContent(body.content),
                updatedBy="user",
            )
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        memory = _toRead(models.getLongTermMemory(db, memoryId))
    notifyMemoryChanged()
    return memory


@router.delete("/{memoryId}", status_code=204)
def deleteMemory(memoryId: int) -> None:
    with database.getDb() as db:
        ok = models.deleteLongTermMemory(db, memoryId)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    notifyMemoryChanged()
