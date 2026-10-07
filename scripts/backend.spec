# -*- mode: python ; coding: utf-8 -*-
"""后端 sidecar 打包：headless（不含 pywebview），由 Tauri 壳拉起。

对应开发文档：docx/v0.1.0/modules/10-打包发布.md（Tauri 迁移）。
"""

import os

# spec 文件在 scripts/ 下，仓库根 = 其上一级
ROOT = os.path.dirname(SPECPATH)

a = Analysis(
    # PyInstaller 按 spec 目录解析脚本路径，必须用绝对路径
    [os.path.join(ROOT, "src", "down_note", "serve.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[
        # 包内预置资源：危机热线（crisis.py 按 __file__ 相对路径找 down_note/resources/）
        (os.path.join(ROOT, "src", "down_note", "resources"), "down_note/resources"),
    ],
    hiddenimports=[
        # uvicorn 动态导入的部件
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # langgraph 的 sqlite checkpoint 插件
        "langgraph.checkpoint.sqlite",
    ],
    excludes=["tkinter", "webview"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="down_note-backend",
    console=False,  # sidecar 无控制台；输出经管道由壳记录
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="down_note-backend",
)
