"""主智能体 graph：承接当前用户会话；消息严格追加保 prefix cache。

工具：getCurrentTime（时间上下文）、queryDiaries（日记查询）、长期记忆增改删查（MEMORY_TOOLS）、
dispatchRecall（火后不理派发回顾子智能体）。
回顾结果由后台线程双写——messages 表（展示）+ update_state（注入主图上下文），
注入受回合闸门约束：回合进行中则等回合结束后注入——不打断、不重说、不丢失。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/01-记忆写入.md
"""

import logging
import threading
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from down_note.agent import llm, recallAgent
from down_note.agent.checkpointer import getCheckpointer
from down_note.agent.context import nowIso
from down_note.agent.tools import MEMORY_TOOLS, getCurrentTime, queryDiaries
from down_note.core.events import broker, turnLock
from down_note.db import database, models

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig

logger = logging.getLogger(__name__)


def buildMainAgent(cfg: "ModelServiceConfig", checkpointer, sessionId: str):
    @tool
    def dispatchRecall(userQuestion: str) -> str:
        """当用户想让你回忆过去的对话（如"还记得我前天说的吗"），把用户原话传入。
        回忆助手会在后台检索，完成后结果会直接出现在对话里。
        你现在只需自然地告诉用户你正在翻记录。"""
        thread = threading.Thread(
                target=runRecallInBackground,
                args=(cfg, sessionId, userQuestion),
                daemon=True,
            )
        thread.start()
        return "回忆助手已在后台开始检索历史会话，完成后结果会直接发到对话里。请告诉用户你正在翻记录，请稍等。"

    tools = [getCurrentTime, queryDiaries, *MEMORY_TOOLS, dispatchRecall]
    model = llm.buildChatModel(cfg).bind_tools(tools)

    def agentNode(state: MessagesState):
        res = model.invoke(state["messages"])
        if not res.tool_calls and not llm.messageText(res):
            # 空回复兜底（推理模型 + 惩罚参数的兼容性问题）：去惩罚参数重试一次；
            # 兜底分支同样绑定工具——否则这一轮模型无工具可调（含记忆写入）
            fallback = llm.buildChatModel(cfg, withPenalties=False).bind_tools(tools)
            res = fallback.invoke(state["messages"])
        return {"messages": [res]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agentNode)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


def runRecallInBackground(cfg: "ModelServiceConfig", sessionId: str, userQuestion: str) -> None:
    """后台执行回顾；结果双写——messages 表（展示）+ update_state（主图上下文）。"""
    try:
        summary = recallAgent.runRecall(cfg, userQuestion)
    except (llm.ModelConfigError, llm.ModelUnavailableError):
        summary = "我暂时翻不了以前的记录，稍后再问问我也行。"
    except Exception:
        logger.exception("会话 %s 回顾失败", sessionId)
        return
    createdAt = nowIso()
    with database.getDb() as db:
        models.addMessage(db, sessionId, "assistant", summary, createdAt)
    with turnLock(sessionId):
        graph = buildMainAgent(cfg, getCheckpointer(), sessionId)
        graph.update_state(
                {"configurable": {"thread_id": sessionId}},
                {"messages": [AIMessage(content=summary)]},
            )
    broker.publish(
            sessionId,
            {"type": "recall", "message": {"role": "assistant", "content": summary, "createdAt": createdAt}},
        )
