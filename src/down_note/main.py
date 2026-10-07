"""应用入口：启动 FastAPI 服务线程与 pywebview 桌面窗口。

页面来源优先级：环境变量 DOWN_NOTE_START_URL > frontend/dist 存在（生产）> Vite 开发服务器。
对应开发文档：docx/v0.1.0/modules/01-项目骨架.md
"""

import ctypes
import os
import threading
import time
import urllib.request
from ctypes import byref, c_int, c_uint

import uvicorn
import webview

from down_note import config
from down_note.app import createApp

HOST = "127.0.0.1"
PORT = 8000
DEV_URL = "http://127.0.0.1:5173"

# 标题栏颜色随应用主题（COLORREF 为 0x00BBGGRR）；Win11 精确生效，Win10 只退深/浅开关
TITLEBAR_DARK = {"caption": 0x00181B1C, "text": 0x00E2EAED}  # 夜笺纸 #1c1b18 / 墨 #edeae2
TITLEBAR_LIGHT = {"caption": 0x00F5F9FA, "text": 0x00181B1C}  # 信笺纸 #faf9f5 / 墨 #1c1b18


def applyTitlebarDark(hwnd: int, isDark: bool) -> None:
    dwm = ctypes.windll.dwmapi
    scheme = TITLEBAR_DARK if isDark else TITLEBAR_LIGHT
    dwm.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1 if isDark else 0)), 4)  # 深色标题栏
    dwm.DwmSetWindowAttribute(hwnd, 35, byref(c_uint(scheme["caption"])), 4)  # 标题栏底色
    dwm.DwmSetWindowAttribute(hwnd, 36, byref(c_uint(scheme["text"])), 4)  # 标题栏文字色


class UiBridge:
    """桌面壳桥：前端把主题同步到窗口标题栏；浏览器环境没有 pywebview，调用静默跳过。"""

    def setTitlebarDark(self, isDark: bool) -> str:
        if os.name != "nt":
            return "unsupported"
        native = getattr(webview.windows[0], "native", None) if webview.windows else None
        handle = getattr(native, "Handle", None)
        if handle is None:
            return "no-window"
        applyTitlebarDark(handle.ToInt32(), isDark)
        return "ok"


def resolveStartUrl() -> str:
    override = os.environ.get("DOWN_NOTE_START_URL")
    if override:
        return override
    frontendDist = config.getBundledRoot() / "frontend" / "dist"
    if frontendDist.exists():
        return f"http://{HOST}:{PORT}/"
    return DEV_URL


def startServer() -> None:
    uvicorn.run(
            "down_note.app:createApp",
            factory=True,
            host=HOST,
            port=PORT,
            log_level="info",
        )


def waitServerReady(timeoutSeconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeoutSeconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/health", timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"后端服务在 {timeoutSeconds} 秒内未就绪：http://{HOST}:{PORT}")


def main() -> None:
    config.loadEnv()
    # daemon 线程：主窗口关闭时随之终止，无需显式 shutdown
    threading.Thread(target=startServer, daemon=True).start()
    waitServerReady()
    webview.create_window(
            "低落日记",
            url=resolveStartUrl(),
            width=1024,
            height=720,
            min_size=(800, 600),
            js_api=UiBridge(),
        )
    webview.start()


if __name__ == "__main__":
    main()
