"""主动陪伴接口：界面活动上报——05 引擎"让路"判据（表二）之一的输入。

前端在"写日记 / 对话中"节流上报（30 秒最多一次）；后端只记时刻，
判定时按 5 分钟有效期算，过期自动失效（不依赖"结束"事件）。
对应开发文档：docx/v0.2.0/modules/05-主动陪伴引擎.md
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from down_note.core import companion

router = APIRouter(prefix="/api/companion", tags=["companion"])


class ActivityReport(BaseModel):
    kind: str


@router.post("/activity")
def reportActivity(body: ActivityReport) -> dict[str, bool]:
    """上报界面活动：kind 只能是 diary（正在写日记）或 chat（正在对话中）。"""
    if body.kind not in companion.ACTIVITY_KINDS:
        raise HTTPException(status_code=400, detail="kind 只能是 diary 或 chat")
    companion.reportActivity(body.kind)
    return {"ok": True}


@router.post("/patrol")
def patrolNow() -> dict:
    """开发自测（托盘「试一次开口」打它）：立刻巡检一次，跳过"等待"，其余判定照常。

    返回 {opened, reason, sessionId}——没开口时 reason 说明是哪条规则拦下的，
    实机测试时不用猜为什么没动静。生成要调模型，响应会等它几秒。
    """
    return companion.patrol(ignoreTiming=True)
