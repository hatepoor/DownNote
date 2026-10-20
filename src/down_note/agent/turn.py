"""主图回合：建图、提示词刷新、回合闸门、流式过滤与落库收在一处。

三个调用点（对话回合 / 唤醒 / 主动开口）只负责造输入消息与消费文本流；
危机回合不走主图流（直连 streamModel），保持原路径，只共用回合闸门。
本模块不认识 HTTP，也不持有降级文案——模型错误原样向外抛，由调用点转成
SSE error 或跳过原因。
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from down_note.agent import llm, mainAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.context import nowIso, refreshSystemPrompt
from down_note.agent.tools import getCurrentTime
from down_note.core.events import turnLock
from down_note.db import database, models

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig


def runAgentTurn(
        cfg: "ModelServiceConfig",
        sessionId: str,
        messages: list[BaseMessage],
        persist: bool = True,
    ) -> Iterator[str]:
    """跑一次主图回合，逐块 yield 文本增量；结束时按 persist 落 messages 表。

    - 异常中途退出不落库（与原实现一致）；调用方提前断开时生成器被关闭，
      锁随 with 语句释放。
    - persist=False 供主动陪伴使用：它要等「空回复 / 目标会话已删除」检查通过后
      自行落库，提前落库会留下孤儿消息。
    """
    replyText = ""
    with turnLock(sessionId):
        graph = mainAgent.buildMainAgent(cfg, getCheckpointer(), sessionId)
        refreshSystemPrompt(graph, sessionId, getCurrentTime.invoke({}))
        for chunk, meta in graph.stream(
                {"messages": messages},
                {"configurable": {"thread_id": sessionId}},
                stream_mode="messages",
            ):
            if meta.get("langgraph_node") != "agent":
                continue
            text = llm.messageText(chunk)
            if text:
                replyText += text
                yield text
        if persist:
            with database.getDb() as db:
                models.addMessage(db, sessionId, "assistant", replyText, nowIso())
