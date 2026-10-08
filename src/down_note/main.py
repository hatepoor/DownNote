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
from pathlib import Path

import uvicorn
import webview

from down_note import config
from down_note.app import createApp

HOST = "127.0.0.1"
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


def applyWindowIcon(hwnd: int, icoPath: Path) -> None:
    """给窗口装上应用图标：标题栏（ICON_SMALL）与任务栏/Alt+Tab（ICON_BIG）。

    仅开发态窗口（本入口）需要——pywebview 不设图标，会显示系统默认的"应用"图；
    安装版由 Tauri 壳按打包配置自带图标（frontend/src-tauri/icons/）。
    """
    user32 = ctypes.windll.user32
    IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE, WM_SETICON = 1, 0x0010, 0x0040, 0x0080
    icon = user32.LoadImageW(
            None,
            str(icoPath),
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )
    if not icon:
        return
    user32.SendMessageW(hwnd, WM_SETICON, 0, icon)
    user32.SendMessageW(hwnd, WM_SETICON, 1, icon)


def getWindowHandle() -> int | None:
    native = getattr(webview.windows[0], "native", None) if webview.windows else None
    handle = getattr(native, "Handle", None)
    return handle.ToInt32() if handle is not None else None


_iconApplied = False


def applyAppIconOnce() -> bool:
    """给窗口补上应用图标（幂等）。返回是否已装上。

    句柄或图标文件还没就绪时返回 False，交给调用方稍后重试。
    """
    global _iconApplied
    if _iconApplied or os.name != "nt":
        return _iconApplied
    icoPath = config.getBundledRoot() / "frontend" / "src-tauri" / "icons" / "icon.ico"
    handle = getWindowHandle()
    if handle is None or not icoPath.is_file():
        return False
    applyWindowIcon(handle, icoPath)
    _iconApplied = True
    return True


def onWindowReady() -> None:
    """窗口就绪回调：等句柄出现后装上应用图标（pywebview 自身不设图标，否则是系统默认图）。

    句柄可能晚于回调就绪，所以轮询几秒；仍拿不到就由前端首次同步主题时再补一次
    （见 UiBridge.setTitlebarDark）。
    """
    for _ in range(15):
        if applyAppIconOnce():
            return
        time.sleep(0.2)


class UiBridge:
    """桌面壳桥：前端把主题同步到窗口标题栏、标题栏按钮控制窗口。

    浏览器环境没有 pywebview，调用静默跳过；Tauri 壳走 Tauri 自己的 API（两者按钮语义一致）。
    """

    def setTitlebarDark(self, isDark: bool) -> str:
        if os.name != "nt":
            return "unsupported"
        applyAppIconOnce()  # 兜底：窗口句柄此刻必定就绪，补上应用图标（幂等）
        handle = getWindowHandle()
        if handle is None:
            return "no-window"
        applyTitlebarDark(handle, isDark)
        return "ok"

    def windowAction(self, action: str) -> str:
        """标题栏按钮：minimize / toggleMaximize / close（无边框窗口由应用自己画标题栏）。"""
        if not webview.windows:
            return "no-window"
        window = webview.windows[0]
        if action == "minimize":
            window.minimize()
        elif action == "toggleMaximize":
            # pywebview 不维护"是否已最大化"的状态（maximized 属性只是构造参数），
            # 所以直接问 Windows：IsZoomed 为真则还原，否则最大化。
            hwnd = getWindowHandle()
            zoomed = bool(hwnd) and bool(ctypes.windll.user32.IsZoomed(ctypes.c_void_p(hwnd)))
            if zoomed:
                window.restore()
            else:
                window.maximize()
        elif action == "close":
            window.destroy()
        else:
            return "unknown-action"
        return "ok"


def resolveStartUrl() -> str:
    override = os.environ.get("DOWN_NOTE_START_URL")
    if override:
        return override
    frontendDist = config.getBundledRoot() / "frontend" / "dist"
    if frontendDist.exists():
        return f"http://{HOST}:{config.getPort()}/"
    return DEV_URL


def startServer() -> None:
    # 工厂对象直接传（同 serve.py：冻结环境里字符串导入不可靠）
    uvicorn.run(
            createApp,
            factory=True,
            host=HOST,
            port=config.getPort(),
            log_level="info",
        )


def waitServerReady(timeoutSeconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeoutSeconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{config.getPort()}/api/health", timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"后端服务在 {timeoutSeconds} 秒内未就绪：http://{HOST}:{config.getPort()}")


def main() -> None:
    config.loadEnv()
    if os.name == "nt":
        # 独立任务栏身份：否则 Windows 把窗口归到 python.exe 名下（图标/分组都不对）
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.hatepoor.downnote")
    # daemon 线程：主窗口关闭时随之终止，无需显式 shutdown
    threading.Thread(target=startServer, daemon=True).start()
    waitServerReady()
    webview.create_window(
            "低落日记",
            url=resolveStartUrl(),
            width=1024,
            height=720,
            min_size=(800, 600),
            frameless=True,  # 无系统标题栏：与应用自绘标题栏一致（安装版 Tauri 壳同款观感）
            easy_drag=True,  # 无边框下靠拖动"拖拽区"移动窗口
            js_api=UiBridge(),
        )
    # 关键：easy_drag 默认"页面任意位置都能拖窗"，会把分隔栏拖拽、文本选择全抢走——
    # 打开此开关后只有带 .pywebview-drag-region 的元素能拖窗（对应 Tauri 的 data-tauri-drag-region）
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    webview.start(onWindowReady)


if __name__ == "__main__":
    main()
