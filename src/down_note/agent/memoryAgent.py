"""记忆管理子智能体 graph：会后维护长期记忆（增/改/删工具调用）。

结构：START → agent（绑工具）→（需要工具？）→ tools → agent → … → 结束。
维护是一次性无状态执行，不挂 checkpointer。
对应开发文档：docx/v0.1.0/modules/07-长期记忆.md
"""

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from down_note.agent import llm
from down_note.agent.prompts import DIARY_MEMORY_PROMPT, MEMORY_MAINTENANCE_PROMPT
from down_note.agent.tools import MEMORY_TOOLS

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig


def buildMemoryAgent(cfg: "ModelServiceConfig"):
    model = llm.buildChatModel(cfg).bind_tools(MEMORY_TOOLS)

    def agentNode(state: MessagesState):
        return {"messages": [model.invoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agentNode)
    builder.add_node("tools", ToolNode(MEMORY_TOOLS))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


def runMemoryMaintenance(
        cfg: "ModelServiceConfig",
        transcript: str,
        memoriesText: str,
        moodsText: str,
    ) -> str:
    """执行一次记忆维护；返回智能体的结语文案（如"新增了一条基本信息"或"无需更新"）。"""
    graph = buildMemoryAgent(cfg)
    result = graph.invoke(
            {
                "messages": [
                    SystemMessage(content=MEMORY_MAINTENANCE_PROMPT),
                    HumanMessage(
                            content=(
                                f"【最近对话】\n{transcript}\n\n"
                                f"【当前长期记忆】\n{memoriesText or '（空）'}\n\n"
                                f"【近期心情记录】\n{moodsText or '（无）'}"
                            )
                        ),
                ]
            }
        )
    return llm.messageText(result["messages"][-1])


def runDiaryMemory(
        cfg: "ModelServiceConfig",
        diaryText: str,
        moodsText: str,
        memoriesText: str,
    ) -> str:
    """每日沉淀：把某天整合后的日记交给记忆管理子智能体（复用同一套工具与去重规则）。"""
    graph = buildMemoryAgent(cfg)
    result = graph.invoke(
            {
                "messages": [
                    SystemMessage(content=DIARY_MEMORY_PROMPT),
                    HumanMessage(
                            content=(
                                f"【这一天的日记】\n{diaryText}\n\n"
                                f"【这天的心情记录】\n{moodsText or '（无）'}\n\n"
                                f"【当前长期记忆】\n{memoriesText or '（空）'}"
                            )
                        ),
                ]
            }
        )
    return llm.messageText(result["messages"][-1])
