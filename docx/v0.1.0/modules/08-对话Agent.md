# 08-对话Agent

## 元信息

- **所属版本**：v0.1.0
- **对应代码**：`src/down_note/agent/mainAgent.py`、`src/down_note/agent/recallAgent.py`、`src/down_note/agent/tools.py`、`src/down_note/agent/prompts.py`、`src/down_note/agent/checkpointer.py`、`src/down_note/api/chat.py`、`frontend/src/views/ChatView.vue`
- **前置依赖**：03-模型接口、05-分析管线（心情记录注入）、06-危机应对、07-长期记忆
- **状态**：已完成（2026-10-06，63 tests passed + 浏览器真实全流程验证）

## 方案要点

- 主智能体 = LangGraph graph：SystemMessage（人设 + 基调 + 长期记忆全量 + 最近日记摘要 + 工具说明）+ HumanMessage/AIMessage 逐轮**追加**，历史永不改写，保 prefix cache。
- 主智能体工具：`获取当前时间`（必备）、`派发回顾`。
- 回顾子智能体：主智能体回答"还记得我前天说的吗"类问题时经工具派发；它用会话检索工具（列会话、取会话消息）读取历史，产出总结文本交回主智能体组织回答。
- 短期记忆载体 = messages 表（追加式，只存 user/assistant 终稿）；**checkpointer（langgraph-checkpoint-sqlite，同库独立表）只做图状态恢复，不是记忆载体**。
- 危机钩子保持在管线层前置：用户输入先进 crisis 初筛/复判，确认危机即切换"共情+资源"应答——不交给模型自主决策。
- v0.1.0 **不做会话压缩、不做上下文超限处理**（已知限度，见 ADR-0005）；超限行为未定义，留给 v0.2.0。

## todolist

- [x] `uv add langgraph langchain-openai langgraph-checkpoint-sqlite`
- [x] agent/llm.py：ChatOpenAI 工厂 + invokeModel/streamModel/messageText/stripCodeFence（03 已就绪，本模块复用）
- [x] agent/tools.py：getCurrentTime、dispatchRecall（主图内定义）、searchSessions/getSessionMessages（RECALL_TOOLS）
- [x] agent/prompts.py：COMPANION_SYSTEM_PROMPT（{memories}/{diaries}/{now} 注入位）、WAKE_INSTRUCTION、RECALL_PROMPT
- [x] agent/mainAgent.py：主 graph（checkpointer 持久化）+ runRecallInBackground——回顾火后不理，结果双写（messages 表 + update_state 注入主图上下文），回合闸门保证注入不打断、不丢失
- [x] agent/recallAgent.py：回顾子 graph（searchSessions + getSessionMessages 工具循环）
- [x] agent/checkpointer.py：SqliteSaver（同库独立表）+ resetCheckpointer（测试用）
- [x] api/chat.py：POST /wake（SSE 开场）、POST /messages（SSE 回合，危机轮旁路 + meta 资源卡）、GET /history（afterId 增量）、GET /sessions（含首条用户消息预览）、GET /events（常驻事件通道，15s 保活）
- [x] core/events.py：EventBroker（进程内发布订阅）+ turnLock（回合闸门）
- [x] agent/context.py：注入材料拼装集中地（scheduler 的 build* 上移）
- [x] 自测（后端）：pytest 60 passed——主图工具循环、回顾派发非阻塞 + 双写 + 注入、SSE 事件序列、危机轮旁路与上下文注入、事件通道、历史/会话列表
- [ ] ChatView.vue：对话界面（消息流、流式渲染、发送、EventSource 接事件通道）
- [ ] 降级模式：对话不可用时的界面态
- [ ] 自测：手工全流程——写日记 → 唤醒 → 对话体现"它读过你的日记" → "还记得我前天说的吗"触发回顾（气泡稍后到达且不打断对话）

- [x] ChatView.vue：对话界面——组件化为 ChatPanel/ChatBubble/HotlineCard/ChatHistoryDrawer，全部实现
- [x] 降级模式：未配置 409 → 降级空态（"它在等一次唤醒"）+ 输入区替换为"仅可记录 · 去配置"；浏览器端降级态走查并入 09 checklist
- [x] 自测：手工全流程（浏览器真实模型）——写日记 → 唤醒（开场白引用昨日摘要 ✓）→ 对话 → "还记得…"（主回合先返、回顾气泡经事件通道稍后自达、不阻塞 ✓）→ 危机句（共情正文流式 + 热线卡 ✓）→ 历史会话抽屉（列表/摘要 ✓）→ 记忆维护真实触发（三会话沉淀两条 psych 条目 ✓）

## 变更记录

- 2026-10-05 重写（原 07-对话Agent 按 LangGraph 多智能体设计重构，拆出 07-长期记忆）
- 2026-10-05 后端批阅实现完成（前端待审阅稿）。关键设计经用户三轮修订：①回顾派发**非阻塞**（火后不理，结果经事件通道回流，轮询方案被否）；②事件注入经回合闸门等回合结束，不打断连贯性、不丢入分支；③危机轮不走主图但经 update_state 保持上下文连贯。踩坑记录：TestClient 的 ASGI 传输会缓冲完整响应，无法消费无限流（事件通道改测生成器本体）；模型池预算要算上 update_state 重建主图的调用；`from down_note import xxx` 路径写错本模块又犯两次（database/models 在 down_note.db、GUIDELINES 在 core.prompts）。
- 2026-10-06 前端批阅实现完成，两大发现：①**defineModel 命名坑**——`defineModel()` 不带名字参数对应裸 v-model（prop叫 modelValue），父组件 `v-model:open` 传不进来，两个抽屉都中招（历史日记抽屉此前也一直打不开）；显式 `defineModel('open', …)` 修复。②**推理模型的 token 预算坑**——思考 token 计入 max_tokens 且长度随机（170~1600+），超预算时正文静默为空：GENERATION_MAX_TOKENS 800→2000 + streamModel 三级兜底（带惩罚流式→无惩罚流式→非流式×2）。另：关键词表补真实变体（撑不住/扛不住/受不了了）；提示词加纯文本约束（禁 Markdown 星号）。HMR 排查插曲：父状态 true 而 prop false 曾误导为 HMR 污染，实为 prop 名不匹配。63 tests passed。
