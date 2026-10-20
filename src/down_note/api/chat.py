"""对话接口：唤醒、回合、历史、会话列表、事件通道、会话删除。

SSE 协议——回合流：start/delta/meta/done/error；事件通道：recall / message（v0.2 起）。
回合执行与回顾注入共用每会话回合闸门；短期记忆双写（messages 表 + checkpointer）。
系统提示词装配（含用户自定义人格）与刷新统一在 agent.context，唤醒与主动开口共用。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.2.0/modules/04-人格模板.md
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from down_note import config
from down_note.agent import llm, mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.context import (
        buildDiariesText,
        buildMemoriesText,
        buildSystemPrompt,
        nowIso,
        primePromptBlocks,
        promptBlocks,
        resolvePersonaText,
    )
from down_note.agent.prompts import WAKE_INSTRUCTION
from down_note.agent.session import dropSession
from down_note.agent.tools import getCurrentTime
from down_note.agent.turn import runAgentTurn
from down_note.core import crisis
from down_note.core.prompts import CRISIS_RESPONSE_GUIDELINES
from down_note.core.events import broker, turnLock
from down_note.db import database, models

router = APIRouter(prefix="/api/chat", tags=["chat"])

MODEL_DOWN_MESSAGE = "它暂时没有回应。你的日记不会受影响，稍后再试试。"


class ChatTurnRequest(BaseModel):
    sessionId: str
    content: str


class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    createdAt: str


class ChatSessionRead(BaseModel):
    sessionId: str
    startedAt: str
    lastActiveAt: str
    preview: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _loadContext() -> tuple:
    """会话级公共装配：配置 + 长期记忆 + 最近日记 + 生效人格（一次性查库）。"""
    with database.getDb() as db:
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            raise HTTPException(status_code=409, detail="未配置模型，无法对话")
        memoriesText = buildMemoriesText(models.listLongTermMemories(db))
        diariesText = buildDiariesText(models.listEntriesWithMood(db, limit=10, offset=0))
        personaText = resolvePersonaText(db)
    return cfg, memoriesText, diariesText, personaText


def _streamAgentTurn(sessionId: str, cfg, messages: list):
    """回合流：主图流式（delta）→ 回复落库 → done；模型失联转 error 事件。"""

    def eventStream():
        yield _sse({"type": "start", "sessionId": sessionId})
        try:
            for text in runAgentTurn(cfg, sessionId, messages):
                yield _sse({"type": "delta", "text": text})
        except (llm.ModelConfigError, llm.ModelUnavailableError):
            yield _sse({"type": "error", "message": MODEL_DOWN_MESSAGE})
            return
        yield _sse({"type": "done"})

    return StreamingResponse(eventStream(), media_type="text/event-stream")


@router.post("/wake")
def wake() -> StreamingResponse:
    """新的唤醒：建会话，主图带着长期记忆、最近日记与生效人格流式开场。"""
    sessionId = uuid.uuid4().hex
    cfg, memoriesText, diariesText, personaText = _loadContext()
    with database.getDb() as db:
        models.upsertChatSession(db, sessionId, nowIso())
    hasDiaries = bool(diariesText)

    systemText = buildSystemPrompt(memoriesText, diariesText, getCurrentTime.invoke({}), personaText)
    messages = [SystemMessage(content=systemText), HumanMessage(content=WAKE_INSTRUCTION)]
    primePromptBlocks(sessionId, promptBlocks(memoriesText, diariesText, personaText))

    def eventStream():
        yield _sse({"type": "start", "sessionId": sessionId, "wakeNote": hasDiaries})
        try:
            for text in runAgentTurn(cfg, sessionId, messages):
                yield _sse({"type": "delta", "text": text})
        except (llm.ModelConfigError, llm.ModelUnavailableError):
            yield _sse({"type": "error", "message": MODEL_DOWN_MESSAGE})
            return
        yield _sse({"type": "done"})

    return StreamingResponse(eventStream(), media_type="text/event-stream")


@router.post("/messages")
def chatTurn(req: ChatTurnRequest) -> StreamingResponse:
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")
    with database.getDb() as db:
        session = models.getSessionById(db, req.sessionId)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        cfg = config.getModelServiceConfig(db)
        if not cfg.isConfigured():
            raise HTTPException(status_code=409, detail="未配置模型，无法对话")
        models.addMessage(db, req.sessionId, "user", content, nowIso())
        models.upsertChatSession(db, req.sessionId, nowIso())

    # 危机两级判定（针对用户输入）：确认危机 → 不走主图，按应答约束流式 + 资源卡
    if crisis.assessEntryText(content, cfg):
        return _crisisTurnStream(req.sessionId, content, cfg)
    return _streamAgentTurn(req.sessionId, cfg, [HumanMessage(content=content)])


def _crisisTurnStream(sessionId: str, content: str, cfg) -> StreamingResponse:
    def eventStream():
        yield _sse({"type": "start", "sessionId": sessionId})
        replyText = ""
        with turnLock(sessionId):
            try:
                guidelines = (
                    CRISIS_RESPONSE_GUIDELINES
                    + "\n\n用中文以“它”的第一人称回复：先共情接住，再自然地把求助热线递给用户。"
                    + "热线号码要清楚完整地给出来。"
                )
                crisisMessages = [
                    SystemMessage(content=guidelines),
                    HumanMessage(content=content),
                ]
                # streamModel 自带空回复兜底（推理模型 + 惩罚参数兼容性）
                for text in llm.streamModel(cfg, crisisMessages):
                    replyText += text
                    yield _sse({"type": "delta", "text": text})
            except (llm.ModelConfigError, llm.ModelUnavailableError):
                yield _sse({"type": "error", "message": MODEL_DOWN_MESSAGE})
                return
            hotlines = crisis.loadHotlines()
            with database.getDb() as db:
                models.addMessage(db, sessionId, "assistant", replyText, nowIso())
            # 危机回合同样进主图上下文（纯状态注入，不触发生成），保持连贯
            graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
            graph.update_state(
                    {"configurable": {"thread_id": sessionId}},
                    {"messages": [HumanMessage(content=content), AIMessage(content=replyText)]},
                )
        yield _sse({"type": "meta", "crisis": True, "hotlines": hotlines})
        yield _sse({"type": "done"})

    return StreamingResponse(eventStream(), media_type="text/event-stream")


@router.get("/history")
def chatHistory(sessionId: str, afterId: int = 0) -> list[ChatMessageRead]:
    with database.getDb() as db:
        messages = models.listMessages(db, sessionId, limit=200)
    return [
            ChatMessageRead(id=m.id, role=m.role, content=m.content, createdAt=m.created_at)
            for m in messages
            if m.id > afterId
        ]


@router.get("/sessions")
def chatSessions() -> list[ChatSessionRead]:
    with database.getDb() as db:
        sessions = models.listRecentSessions(db, limit=20)
        result = [
                ChatSessionRead(
                        sessionId=s.session_id,
                        startedAt=s.started_at,
                        lastActiveAt=s.last_active_at,
                        preview=models.firstUserMessage(db, s.session_id) or "（无消息）",
                    )
                for s in sessions
            ]
    return result


@router.delete("/sessions/{sessionId}", status_code=204)
def deleteChatSession(sessionId: str) -> None:
    """删掉这次对话本身：图状态、消息、会话行、提示词快照一次清，幂等。

    长期记忆一律不动（用户口径："只删这次对话，仅此而已"）；重复删除无副作用。
    """
    dropSession(sessionId)


async def chatEventStream(sessionId: str):
    """事件流生成器（独立函数便于直接测试——TestClient 的 ASGI 传输会缓冲完整响应，无法测无限流）。"""
    queue = broker.subscribe(sessionId)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield _sse(event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        broker.unsubscribe(sessionId, queue)


@router.get("/events")
async def chatEvents(sessionId: str):
    """常驻事件通道：后台任务（回顾完成等）实时推送；15 秒无事件发注释帧保活。"""
    return StreamingResponse(chatEventStream(sessionId), media_type="text/event-stream")
