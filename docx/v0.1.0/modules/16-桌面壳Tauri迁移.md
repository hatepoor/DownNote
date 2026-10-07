# 16-桌面壳 Tauri 迁移

## 元信息

- **所属版本**：v0.1.1
- **对应代码**：`frontend/src-tauri/`（Rust 壳）、`src/down_note/serve.py`、`scripts/backend.spec`、`scripts/build.py`、`frontend/src/components/TitleBar.vue`、`frontend/src/api/client.ts`
- **前置依赖**：10-打包发布
- **状态**：已完成（2026-10-07）
- **备注**：应用壳从 pywebview 迁移到 Tauri 2；Vue 前端与 Python 后端零重写

## 方案要点

1. **动机**：pywebview 的标题栏只跟系统主题（白条）、窗口与页面风格脱节；Tauri 2 提供无边框自绘标题栏、Mica 云雾（后续）、原生窗口动画、单实例、自带 NSIS 中文打包。
2. **架构**：Tauri 壳（Rust）从 resources 拉起 **Python 后端 sidecar**（PyInstaller onedir，headless 无 pywebview），传 `DOWN_NOTE_PORT=<随机空闲端口>`；壳轮询端口就绪后显示窗口（防启动闪白）；前端经 `invoke('backend_port')` 拿端口，所有请求打 `http://127.0.0.1:<port>`。窗口关闭/任何退出路径都 kill 后端。
3. **前端改动（点状）**：`api/client.ts` 加 `apiBase()`（Tauri 下 invoke 取端口、浏览器/Vite 走相对路径）+ 统一 `api()` 入口；图片地址 `withImageBase` 拼基址；`TitleBar.vue`（`data-tauri-drag-region` 拖拽 + 最小化/最大化/关闭，仅 Tauri 环境渲染）；`stores/appState.ts` 导出 `isTauri`。
4. **后端改动（点状）**：`config.getPort()`（`DOWN_NOTE_PORT`，默认 8000）；`down_note/serve.py`（headless 入口）；`scripts/backend.spec`（sidecar 打包，excludes webview）。开发模式 `python -m down_note.main`（pywebview 窗口）保留。
5. **布局**：`src-tauri` 放在 `frontend/` 内（Tauri CLI 只在 cwd 向下找 `tauri.conf.json`，且 before*Command 需要跑在 package.json 所在目录）。

## todolist

- [x] 环境：Rustup（stable-msvc）+ VS Build Tools C++ 工作负载
- [x] src-tauri 骨架：conf / main.rs / capabilities / 图标
- [x] sidecar 拉起 + 健康等待 + 端口下发 + 退出回收 + 单实例
- [x] 前端基址层 + 自绘标题栏 + 唤醒自动发送
- [x] build.py 新链路 + NSIS 简中安装包
- [x] 安装版实装/卸验证（sidecar 随机端口 + 真实数据）
- [x] Release v0.1.1 发布

## 变更记录

- 2026-10-07 创建并完成（用户选型 Tauri 2；审阅稿批复后实施）。

## 踩坑记录（全部实测）

1. **Tauri CLI 只在 cwd 向下找 `tauri.conf.json`**——`src-tauri` 必须位于调用 CLI 的目录之内（放 `frontend/src-tauri`，从 frontend 调 `npm run tauri`）。
2. **`bundle.resources` 的 glob 不递归**：`dir/*` 只拷匹配条目、目录（如 `_internal/`）会丢；用**目录路径本身**（`resources/backend`）才整目录递归拷贝，且按 conf 相对路径落位（`resource_dir()/resources/backend/...`）。
3. **跨出 conf 目录的资源引用**（`../../dist/...`）会被 NSIS 转成 `_up_/_up_/...` 嵌套目录，运行时路径对不上——资源必须先进 `src-tauri` 内（build.py 负责拷）。
4. **uvicorn 字符串导入在冻结环境失效**：`uvicorn.run("down_note.app:createApp")` 在 PyInstaller 下 `Could not import module "down_note.app"`（字符串动态导入不被静态打包）——改为 `uvicorn.run(createApp, factory=True)` 直接传工厂对象（serve.py 与 main.py 统一）。
5. **MSYS 路径转换吃掉安装器开关**：Git Bash 里 `/S` 会被当 POSIX 路径改写，调用 Windows 安装器一律加 `MSYS_NO_PATHCONV=1` 前缀。
6. `w.emit` 在 Tauri 2 需要 `use tauri::Emitter;`（emit 移入了 Emitter trait）。
7. build.py 子进程的 PATH 不含 `~/.cargo/bin`，需自行补（`os.environ["PATH"] += ...`）。
8. **无控制台启动时 stdout/stderr 为 None**：双击运行（无控制台可继承）时 PyInstaller 的 `sys.stdout/stderr` 是 None，uvicorn 日志格式化器做 isatty() 彩色检测直接崩（`'NoneType' object has no attribute 'isatty'`，弹 Unhandled Exception 框）——`serve.py` 在 import uvicorn 前给 None 的 stdout/stderr 挂 `os.devnull`。**冒烟必须用分离启动复现**（PowerShell `Start-Process`），从终端启动有 stdout 继承、这个坑暴露不出来。
9. **窗口缩放不触发分栏宽度钳制**：`diaryWidth` 只在拖动与挂载时钳制——大窗（最大化）下拖出的宽度存进 localStorage 后，还原小窗时对话栏（`min-width:0`）被整根压没。App.vue 监听 `window resize` 重新钳制（公式含窄栏 64 + 分栏命中区 9 + 对话栏最小 360）。
10. **壳内页面对本地后端是跨源的**：Tauri 页面源为 `http(s)://tauri.localhost`，向 `127.0.0.1:<port>` 的 fetch/EventSource 全是跨源请求——GET 简单请求尚可通过，PUT/自定义头会先发 OPTIONS 预检，后端没有 CORS 中间件时预检 405，页面表现为 "Failed to fetch"（读取正常、保存失败）。修法 = app.py 挂 `CORSMiddleware`（放行 `http(s)://tauri.localhost` 与开发源 `127.0.0.1:5173`）。**冒烟要模拟预检**：`curl -X OPTIONS` 带 Origin + Access-Control-Request-Method。
