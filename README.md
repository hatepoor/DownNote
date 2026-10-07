<div align="center">
  <img src="front_design/app-icon/png/icon-256.png" width="88" alt="低落日记">
  <h1>低落日记</h1>
  <p><strong>一本会陪你说话的日记 · 开源 · 本地运行 · 无账号</strong></p>
  <p>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
    <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12">
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey" alt="Windows">
  </p>
</div>

---

低落日记，就像它的名字一样。

我们往往有很多时候陷入到低落的情绪当中。有时睡一觉，吃点蛋糕，或者单独放松放松，这种低落的情绪就过去了。

但，我们真的有正视过这种情绪吗？我们习惯于用各种各样的事情来逃避它，却忘了解决它。大多数时候，我们没有足够的勇气去面对，于是将它耽搁起来不管不理——但它从未消失，它仍然在那里，在我们开心时那个看不到的阴暗角落中。

我想做这个项目，用来记录自己的低落情绪，记录每个时刻自己那些不开心的时候。

当然，它不是一个单纯的笔记工具。

而是一个 agent——一个接纳你所有低落情绪的 agent。你的情绪，它都读得到；在你低落的时候，陪你说说话。

## 功能一览（v0.1.0）

- **记录**：文字 + 图片，随时写下此刻的心情
- **心情记录**：每条日记后台自动分析，产出情绪标签、强度与一句摘要
- **唤醒对话**：多智能体陪伴聊天，开口前它会先读你最近写下的日子
- **跨天整合**：一天结束时自动把当天条目整合成一篇日记，模型分析"这一天的心情"，并沉淀为长期记忆
- **危机应对**：关键词初筛 + 模型复判，先共情接住，再温和给出求助资源；不评判、不中断
- **长期记忆**：完全透明——可查看、可编辑、可删除，智能体维护与你的手写同等有效
- **体验细节**：日/夜双主题、Markdown 渲染、历史按天浏览、过去的日记锁定不可改、可拖拽分栏

## 下载使用

1. 从 [Releases](../../releases) 下载 `down_note-v0.1.0-win64.zip`，解压到任意位置
2. 双击 `down_note.exe`——不需要安装 Python 或 Node
3. 首次启动自动建库；点左侧栏「设置」配置模型，保存即生效

几点说明：

- 仅支持 **OpenAI 兼容**服务，Base URL 填到 `/v1` 一层即可。OpenAI、DeepSeek、通义千问（compatible-mode）、本地 Ollama 都可以：
  ```
  https://api.openai.com/v1
  https://dashscope.aliyuncs.com/compatible-mode/v1
  http://127.0.0.1:11434/v1   （Ollama）
  ```
- 未配置模型也能写日记（**降级模式**：记录永不失能）；配置后分析与对话自动恢复
- 模型的温度、思考强度可在设置里调整（默认 1.1 / low），真实作用于每次调用
- Windows 10 若窗口空白，安装一次 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)（Win11 自带）
- 未做代码签名，首次运行 SmartScreen 提示时选「更多信息 → 仍要运行」

## 数据与隐私

- 日记、心情记录、长期记忆保存在**本机** SQLite（Windows：`%APPDATA%\down_note`），不回传任何自有服务器
- 唯一出网的调用是你对模型服务的请求：日记原文按你的配置直发你自选的模型服务，隐私权衡在你
- API Key 只存本机 `.env`（模板见 [.env.example](.env.example)），永不上传、不进数据库
- 求助热线可自定义：在数据目录放一份 `hotlines.json` 即可覆盖内置数据

## 危机应对与免责

低落日记不是医疗产品，也不能替代专业帮助。若你正处于危机之中，请优先联系专业机构或当地求助热线（应用也会在你需要时展示热线资源）。

## 从源码运行

环境要求：Python 3.12（推荐用 [uv](https://docs.astral.sh/uv/) 管理）+ Node.js 18+

```bash
git clone https://github.com/hatepoor/DownNote.git
cd down_note
uv sync                                  # 后端依赖
cd frontend && npm install && cd ..      # 前端依赖
uv run pytest                            # 跑测试（79 个）
uv run python -m down_note.main          # 启动桌面应用
```

- 开发模式：`cd frontend && npm run dev`，应用窗口/浏览器会自动走 Vite 热更新
- 打包发布：`uv run python scripts/build.py` → 产出 `dist/down_note/`，整目录压缩即为发布 zip

## 目录结构

```
down_note/
├─ src/down_note/     # 后端：FastAPI + LangGraph 多智能体 + SQLite
├─ frontend/          # 前端：Vue 3（Vite + TS）
├─ scripts/           # 打包脚本（entry / spec / build）与发布说明
├─ docs/              # ADR 决策记录、Release 说明草稿
├─ docx/              # 开发文档：需求、架构、模块 todolist、进度树
├─ front_design/      # 前端设计定稿与应用图标
└─ tests/             # pytest 测试
```

## 技术栈

Vue 3（Vite + TypeScript）· Python 3.12 · FastAPI · SQLAlchemy + SQLite · APScheduler · LangGraph · pywebview · PyInstaller

## License

[MIT](LICENSE)
