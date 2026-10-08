"""进程内事件总线 + 每会话回合闸门。

事件总线：后台任务完成 → 前端推送（每会话常驻 SSE 事件流订阅，无订阅者时事件自然消散）；
分析状态与长期记忆变更也走同一总线（ENTRY_EVENTS_CHANNEL / MEMORY_EVENTS_CHANNEL，
全局频道，单用户应用不分会话）。
回合闸门：回合执行与回顾注入互斥——注入永不打断回合、永不丢失（等回合结束再写）。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md、docx/v0.1.2/modules/02-分析提速.md、
docx/v0.1.2/modules/10-记忆即时可见.md
"""

import asyncio
import json
import threading

ENTRY_EVENTS_CHANNEL = "entries"  # 分析状态推送频道（单用户应用，不分会话）
MEMORY_EVENTS_CHANNEL = "memories"  # 长期记忆变更推送频道（同上，全局）


def sseFrame(event: dict) -> str:
    """SSE 数据帧（与对话事件流同格式）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class EventBroker:
    def __init__(self) -> None:
        self._subscriptions: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, sessionId: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscriptions.setdefault(sessionId, set()).add((loop, queue))
        return queue

    def unsubscribe(self, sessionId: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscriptions.get(sessionId, set())
            for item in list(subscribers):
                if item[1] is queue:
                    subscribers.discard(item)

    def publish(self, sessionId: str, event: dict) -> None:
        """任意线程可调：把事件投递到该会话所有订阅者的事件循环。"""
        with self._lock:
            targets = list(self._subscriptions.get(sessionId, ()))
        for loop, queue in targets:
            loop.call_soon_threadsafe(queue.put_nowait, event)


broker = EventBroker()


def notifyMemoryChanged() -> None:
    """长期记忆新增 / 修改 / 删除成功后调用：通知前端刷新记忆列表。任意线程可调。"""
    broker.publish(MEMORY_EVENTS_CHANNEL, {"type": "memory"})


_turnLocks: dict[str, threading.Lock] = {}
_locksGuard = threading.Lock()


def turnLock(sessionId: str) -> threading.Lock:
    """每会话一把回合闸门：回合执行与回顾注入互斥。"""
    with _locksGuard:
        return _turnLocks.setdefault(sessionId, threading.Lock())
