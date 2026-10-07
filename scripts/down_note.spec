# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：onedir 模式，数据文件含 frontend/dist 与包内资源。

对应开发文档：docx/v0.1.0/modules/10-打包发布.md；构建一律走 scripts/build.py。
"""
import os

# spec 文件在 scripts/ 下，仓库根 = 其上一级；datas/图标相对根定位，不依赖执行目录
ROOT = os.path.dirname(SPECPATH)

a = Analysis(
    # PyInstaller 按 spec 目录解析脚本路径，这里必须用绝对路径
    [os.path.join(ROOT, "scripts", "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[
        # 前端构建产物（build.py 会先 npm run build）
        (os.path.join(ROOT, "frontend", "dist"), "frontend/dist"),
        # 包内预置资源：危机热线（crisis.py 按 __file__ 相对路径找 down_note/resources/）
        (os.path.join(ROOT, "src", "down_note", "resources"), "down_note/resources"),
    ],
    hiddenimports=[
        # uvicorn 动态导入的部件（缺了表现为服务起不来）
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # pywebview Windows 后端（EdgeChromium 经 pythonnet）
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        # langgraph 的 sqlite checkpoint 插件；langchain 系构建/运行报缺再逐个补
        "langgraph.checkpoint.sqlite",
    ],
    excludes=["tkinter"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="down_note",
    console=False,  # 桌面应用不开控制台；排查打包问题时临时改 True 看日志
    icon=os.path.join(ROOT, "front_design", "app-icon", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,  # 不做 UPX 压缩：减小被杀软误报的概率
    name="down_note",
)
