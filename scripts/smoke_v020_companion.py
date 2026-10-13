"""04+05 端到端冒烟（仓库代码 + 临时数据目录 + 假模型）：不依赖真实模型端点。

跑法：DOWN_NOTE_DATA_DIR=<临时目录> uv run python <本脚本>
验证链：写 soul.md 并开启 → patrol 主动开口 → 生成落库 → 系统提示词里是自定义人格。
"""

import json
import os
import sys
from datetime import datetime, time as clockTime, timedelta

from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from down_note import config
from down_note.agent import llm as agentLlm
from down_note.agent.checkpointer import getCheckpointer
from down_note.core import companion, persona
from down_note.db import database, models


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


REPLY = "（冒烟）在忙吗，我随口说一句"


def main() -> int:
    assert os.environ.get("DOWN_NOTE_DATA_DIR"), "必须指向临时数据目录"
    agentLlm.buildChatModel = lambda cfg, **kw: FakeToolModel(messages=iter([AIMessage(content=REPLY)]))
    database.ensureSchema()

    # ① 人格（04）：写入 soul.md 并开启
    customPersona = "你是一个话很少的朋友，句子很短。"
    persona.writeCustomPersona(customPersona)
    with database.getDb() as db:
        models.setSetting(db, "base_url", "http://model.local/v1")
        models.setSetting(db, "model_name", "smoke")
        models.setSetting(db, persona.PERSONA_ENABLED_KEY, "1")
        models.setSetting(db, companion.ENABLED_KEY, "1")
        models.setSetting(db, companion.TIER_KEY, "caring")

    # ② 巡检（05）：注入窗口内时刻，并把启动缓冲基准挪到该时刻之前
    patrolAt = datetime.combine(datetime.now().date(), clockTime(15, 0))
    companion.markProcessStart(patrolAt - timedelta(hours=1))
    companion.patrol(patrolAt)

    # ③ 结果核对
    with database.getDb() as db:
        sessions = models.listRecentSessions(db, limit=5)
        assert len(sessions) == 1, f"应新建 1 个会话，实际 {len(sessions)}"
        sessionId = sessions[0].session_id
        rows = models.listMessages(db, sessionId)
        state = json.loads(models.getSetting(db, companion.STATE_KEY) or "{}")

    print("会话数 =", len(sessions))
    print("落库消息 =", [(m.role, m.content) for m in rows])
    print("引擎状态 =", state)
    assert [(m.role, m.content) for m in rows] == [("assistant", REPLY)], "主动开口未落库"
    assert state["dayCount"] == 1 and state["missed"] == 1, "状态未推进"

    checkpoint = getCheckpointer().get_tuple({"configurable": {"thread_id": sessionId}})
    systems = [
            message
            for message in checkpoint.checkpoint["channel_values"]["messages"]
            if message.type == "system"
        ]
    assert len(systems) == 1, "系统提示词条数不对"
    systemText = systems[0].content
    print("系统提示词开头 =", systemText[:40])
    print("含自定义人格 =", systemText.startswith(customPersona))
    print("含工具与边界 =", "工具与边界：" in systemText)
    assert systemText.startswith(customPersona), "自定义人格未进提示词"
    assert "工具与边界：" in systemText, "固定段丢失"
    assert "怎么说话（最重要）" not in systemText, "默认风格层没被替换"

    print("\n端到端冒烟通过：soul.md → 提示词 → 主动开口落库 → 状态推进")
    return 0


if __name__ == "__main__":
    sys.exit(main())
