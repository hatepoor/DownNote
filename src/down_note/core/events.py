"""进程内事件总线 + 每会话回合闸门。

事件总线：后台任务完成 → 前端推送（每会话常驻 SSE 事件流订阅，无订阅者时事件自然消散）；
回合闸门：回合执行与回顾注入互斥——注入永不打断回合、永不丢失（等回合结束再写）。
对应开发文档：docx/v0.1.0/modules/08-对话Agent.md
"""

import asyncio
import threading


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

_turnLocks: dict[str, threading.Lock] = {}
_locksGuard = threading.Lock()


def turnLock(sessionId: str) -> threading.Lock:
    """每会话一把回合闸门：回合执行与回顾注入互斥。"""
    with _locksGuard:
        return _turnLocks.setdefault(sessionId, threading.Lock())
