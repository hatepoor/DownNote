# AGENTS.md — 低落日记（down_note）

## 项目是什么

开源、本地运行的单用户情绪陪伴桌面应用：无账号体系、无自有服务器、无多用户。
`README.md` 是项目主页（产品愿景 + 使用与开发指南，面向 GitHub 访客）；`CONTEXT.md` 是唯一术语表，是本项目的一致性语言——**写任何代码或文档前先读它**，命名必须使用其中术语，禁止自造同义词（"情绪记录""人设""推送"等均为禁用说法）。
开发进度看 `docx/README.md`（版本路线图 + 进度树）；**动手改代码前先读对应模块文档** `docx/v0.1.0/modules/`（任务级 todolist 在里面）；前端设计方案在 `front_design/`，改界面前先读。

## 当前状态

- 设计已收口，文件树与 v0.1.0 文档体系已建立；`src/`、`frontend/`、`tests/` 按各模块文档的 todolist 逐个推进（01-10、11-16 已完成；v0.1.1 已发布——桌面壳迁移 Tauri 2，干净机器验证待做）。技术形态已定：Vue（Vite）前端 + Python（FastAPI + APScheduler + SQLAlchemy + SQLite）后端，智能体层用 LangGraph 多智能体（主智能体 + 回顾/记忆管理子智能体，ADR-0005），桌面壳 **Tauri 2**（`frontend/src-tauri/`，Rust 壳 + 后端 PyInstaller sidecar，见模块 16）。
- 实测已确认：用户 model 为推理型（deepseek v4.1 flash，思考 token 计入 max_tokens 且长度随机），生成参数可由用户在设置里调整（温度默认 1.1、思考强度默认 low，存 settings 表，`buildChatModel` 真实应用），其余固定项与三级流式兜底不可动；危机关键词表中的变体来自真实对话验证，改动需谨慎。
- Python 环境已用 uv 初始化：Python 3.12，虚拟环境 `.venv/`，依赖清单 `pyproject.toml`，锁文件 `uv.lock`。
- 四条 ADR 已落盘 `docs/adr/`；当前版本总纲在 `docx/v0.1.0/README.md`（含里程碑与待定决议）。
- 尚未初始化 git 仓库（`.gitignore` 已备好）。
- 开发者环境：Windows，Shell 为 Git Bash / PowerShell。

## 环境与版本管理（uv）

- Python 解释器版本与依赖版本统一由 **uv** 管理：版本钉在 `.python-version`（3.12），依赖声明在 `pyproject.toml`，精确版本锁定在 `uv.lock`。三者都要提交；`.venv/` 不提交（已加入 `.zcodeignore`）。
- 添加依赖一律 `uv add <包名>`，开发依赖用 `uv add --dev`；禁止手动 pip install 或只改 `pyproject.toml` 不更新锁文件。
- 运行一律 `uv run <命令>`（如 `uv run python`、`uv run pytest`），不手动激活虚拟环境。
- 拉取代码或依赖变更后执行 `uv sync` 同步 `.venv`。

## Python 编码风格（强制）

编写、修改、生成任何 Python 代码前，必须先读 `C:\Users\20624\.agents\skills\python-camel-style\SKILL.md` 并严格遵循——即使用户没提"风格"字眼，即使触发 linter 报警。核心规则（全文以 skill 为准）：

- **驼峰命名**：变量、函数、参数、方法、实例属性一律 camelCase；类名 PascalCase；常量 UPPER_SNAKE_CASE；私有 `_camelCase`；字典字面量与 JSON 键名同样驼峰。禁止 snake_case。
- **强制例外（不得改名）**：dunder 方法、import 进来的标识符及其参数、pytest 的 `test_` 函数与 fixture、装饰器及其参数、数据库/外部服务约定好的字段名——跟着对方定义走。
- **悬挂缩进**：多行调用续行缩进 8 格，闭括号与语句首行对齐；**尾逗号**：展开后每项带逗号（含最后一项）；**一行一参数**：单行超 100 字符或参数多于 3 个才展开。
- **避免正则**：优先字符串内建方法（`in`、`split`、`startswith`、`partition` 等）；确需 `import re` 必须注释说明原因。
- **遗留代码**：已有的 snake_case 不顺手改、不做整文件重命名；ruff 的 pep8-naming（N 规则）报警属预期，忽略即可，不改 ruff 配置。

## MVP 边界（第一版只做）

记录（文字 + 图片）→ 后台分析（产出心情记录）→ 唤醒对话。危机应对（关键词初筛 + LLM 复判，姿态为共情 + 提供求助资源）随分析/对话链路进第一版。跨天后日整合（11 模块）：当天条目纯程序整合成一篇日记，模型分析出日心情并从中沉淀长期记忆。

第二波再做，**不要提前实现**：定时关怀、信号触发、人格模板、回顾可视化、设置界面、密钥加密存储。

## 产品不变量（改代码时不得破坏）

- **记录永不因 Agent 失能而不可用**：未配置模型或调用失败时进入"降级模式"，日记功能完整可用，主动关怀与分析暂停。
- 模型接口**只做 OpenAI 兼容协议**（Base URL + API Key + 模型名三件套），配置即换；日记原文直发用户自配的模型，不做脱敏。
- 危机信号处理姿态：先共情接住，再温和提供求助资源，不评判、不中断、不上报。
- 长期记忆对用户完全透明：可查看、可编辑、可删除；智能体维护与用户编辑同等有效，不设修改锁。
- 情绪数据只存本地 SQLite，不回传任何自有服务端。

## 协作模式（由用户声明）

项目开发按用户声明的模式进行：

1. **自动模式**：所有代码由助手直接编写并验证，无需逐步过问。
2. **批阅模式**：先给出代码供用户审阅，用户同意后再写入文件；期间用户可能对代码提问。
3. **教学模式**：给出代码与讲解，由用户亲手编写；助手负责测试代码与验证。

注：无论当前处于何种模式，用户声明"你来写"时，该轮代码由助手直接编写。

## 约定

- 全部文档、注释、UI 文案使用中文。
- 术语分界易错，不要混用：**心情记录** = 从日记条目提炼出的情绪数据；**性格画像** = 描述用户（可见、可改、可删）；**人格模板** = 定义 Agent 的陪伴风格。
- 常用命令：测试 `uv run pytest`；启动应用（自动识别 dev/prod 页面来源）`uv run python -m down_note.main`；前端开发服务器在 `frontend/` 下 `npm run dev`；打包 `uv run python scripts/build.py`（产物 `dist/down_note/`，整目录压缩即为发布 zip；压缩前先关掉运行中的 exe）。
