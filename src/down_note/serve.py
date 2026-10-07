"""headless 服务入口：Tauri 壳以 sidecar 方式拉起，只起 API、不开桌面窗口。

端口来自 DOWN_NOTE_PORT（壳分配的随机空闲端口），默认 8000。
.env 加载 / 建表 / 调度由 app 工厂的 lifespan 统一完成。
注意：uvicorn 传工厂**对象**而非 "module:attr" 字符串——字符串导入在
PyInstaller 冻结环境里找不到未静态引用的模块。
对应开发文档：docx/v0.1.0/modules/10-打包发布.md
"""

import os
import sys

# 双击启动（无控制台）时 stdout/stderr 为 None，uvicorn 等库做 isatty()
# 彩色检测会直接崩（'NoneType' object has no attribute 'isatty'）——
# 先挂上空设备再继续。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import uvicorn

from down_note import config
from down_note.app import createApp

if __name__ == "__main__":
    uvicorn.run(
            createApp,
            factory=True,
            host="127.0.0.1",
            port=config.getPort(),
        )
