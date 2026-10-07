"""回顾子智能体 graph：检索历史会话并总结，回答"还记得……吗"类问题。

被主智能体的 dispatchRecall 工具在后台线程派发；与维护图同构（单节点 + 工具循环）。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md
"""

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from down_note.agent import llm
from down_note.agent.prompts import RECALL_PROMPT
from down_note.agent.tools import RECALL_TOOLS

if TYPE_CHECKING:
    from down_note.config import ModelServiceConfig

_RECALL_TOOLS = RECALL_TOOLS


def buildRecallAgent(cfg: "ModelServiceConfig"):
    model = llm.buildChatModel(cfg).bind_tools(_RECALL_TOOLS)

    def recallNode(state: MessagesState):
        return {"messages": [model.invoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("recall", recallNode)
    builder.add_node("tools", ToolNode(_RECALL_TOOLS))
    builder.add_edge(START, "recall")
    builder.add_conditional_edges("recall", tools_condition)
    builder.add_edge("tools", "recall")
    return builder.compile()


def runRecall(cfg: "ModelServiceConfig", userQuestion: str) -> str:
    result = buildRecallAgent(cfg).invoke(
            {"messages": [SystemMessage(content=RECALL_PROMPT), HumanMessage(content=userQuestion)]}
        )
    return llm.messageText(result["messages"][-1])
