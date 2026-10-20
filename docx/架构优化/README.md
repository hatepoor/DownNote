# 架构优化（跨版本工程债）

> 定位：**不属于任何版本范围**，不参与版本号，不改变产品功能与用户可见行为。
> 目的：消除架构摩擦（seam 不齐、浅模块、复杂度分布错位），提升可测性与可维护性。
> 方法来源：`improve-codebase-architecture` + `codebase-design`（深模块 / 深度的度量口径）。
> 评审基线：2026-10-20，main 分支近 60 次提交热点（`app.py`、`scheduler.py`、`core/events.py`、`api/entries.py`、`App.vue`）。
> 可视化评审报告：[评审报告-2026-10-20.html](./评审报告-2026-10-20.html)（浏览器打开，含 Before/After 图）。

## 一、术语口径（全文统一）

本目录只用 `codebase-design` 的词汇，不用"组件 / 服务 / API / 边界"：

- **module**：有 interface 与 implementation 的任何东西（函数、类、包、跨层切片均可）。
- **interface**：调用方必须知道的全部事实——签名、不变量、顺序约束、错误模式、必需配置。
- **depth**：interface 处的 Leverage。行为多、interface 小 = **deep**；interface 几乎与 implementation 等大 = **shallow**。
- **seam**：可以不改动该处代码就改变行为的位置，即 module interface 所在之处。
- **adapter**：在 seam 上满足 interface 的具体实现。
- **leverage**：调用方按 interface 获得的收益；**locality**：维护者获得的收益（改动、bug、验证集中在一处）。

判定工具：**deletion test**——删掉它，复杂度是集中了（保留）还是换个地方（可删）？

## 二、总体判断

深模块基准在本库已经存在：`agent/llm.py`（工厂 + 错误归类 + 三级兜底，interface 远小于 implementation）、`core/signals.py`（判据纯程序 + 冷却读写，可注入 `db` / `now` 直测）——两者是全库正面样板。

摩擦不在"某个 module 太深或太浅"，而在 **seam 用得不整齐**：同一类问题（settings 键归属、数据访问入口、回合执行）在不同模块用了不同规则，正确性靠人肉记忆维持。

## 三、候选总览

| # | 候选 | 强度 | 批次 | 主要收益 | ADR / 文档冲突 |
|---|---|---|---|---|---|
| 1 | 主图回合深 module（消四处 stream 样板） | Strong | A | leverage：interface 收缩；测试不摸 LangGraph 内部形状 | 无 |
| 2 | settings 键单一归属 + 巡逻旗标具名化 | Strong | A | 消除"编译期不报错、实机才发现"的隐患 | 无 |
| 3 | db seam 收口（收编 `db.get` 裸调用、`entryToRead` 自取数据） | Strong | B | seam 一种用法，访问面可推断 | 与 ADR-0006 同向 |
| 4 | 会话生命周期收口（`dropSession` 一次调用） | Worth exploring | B | locality：删除语义一处可见 | 无 |
| 5 | 主动开口链路归位（scheduler 纯注册 + 因果链显式） | Worth exploring | C | locality：任务实现与判定各归其位 | 05 模块文档约束判定不得进模型 |
| 6 | `agent/tools` 浅 module 群按域合并 | Worth exploring | 挂起 | interface 不变、跳转少两层 | **与 docx/v0.1.2/modules/00-结构重构.md 冲突** |
| 7 | 前端壳 adapter 独立 + 通知 pending 合一 | Speculative | D | 两段同名 pending 合一，状态文件只剩状态 | 无 |

批次含义见第五节。每批独立可交付、可回滚，互不阻塞。

## 四、候选详情

### 候选 1（Strong）· 主图回合深 module

**涉及文件**（行号以当前 main 为准，实施时重新定位）：

- `src/down_note/api/chat.py:79-107`（`_streamAgentTurn`）、`:123-147`（`wake` 内联流循环）、`:197-201`（危机回合 `update_state` 注入）
- `src/down_note/core/companion.py:169-189`（`_generateOpening`）
- `src/down_note/agent/mainAgent.py:32-64`（只建图，不拥有"回合"）
- `tests/test_companion_engine.py:47-55`（伪造 chunk/meta 形状才能测试）

**现状**：跑一次主图回合的完整知识——建图 → `refreshSystemPrompt` → `turnLock(sessionId)` → `graph.stream(stream_mode="messages")` → 过滤 `meta["langgraph_node"] != "agent"` → 文本累加 → 落 messages 表——在**三个调用点**（`chatTurn` 回合、`wake` 唤醒、主动开口）各复制一遍；危机回合不走主图流（直连 `llm.streamModel`），但同样复制了闸门与落库，并额外做一次 `update_state` 注入。LangGraph 的 stream 原生 interface 泄漏进 api 层与 core 层。

三处落库语义有一处实质差异：主动开口**不能**提前落库——它要等「空回复 / 目标会话已删除」检查通过后才写，否则会留下孤儿消息。因此回合 module 需要一个 `persist` 参数，而不是无脑落库。

**deletion test**：删掉四处样板换成一个深 module，复杂度真正集中（过滤规则、闸门顺序只存在一份）；反过来内联只是搬家。结论：抽取成立。

**方案**：新增 `src/down_note/agent/turn.py`，对外只暴露一个 interface：

```python
def runAgentTurn(
    cfg,                   # 模型配置（三件套）
    sessionId: str,
    messages: list,        # 本次输入消息
    persist: bool = True,  # 是否落 messages 表（危机注入回放等场景可关）
):
    """生成器：逐块 yield 文本增量，内部完成闸门、提示词刷新、chunk 过滤、落库。"""
```

内部实现顺序（唯一一份，写进 docstring）：

1. `buildMainAgent(cfg, getCheckpointer(), sessionId)`
2. `refreshSystemPrompt(graph, ...)`
3. `with turnLock(sessionId):`
4. `graph.stream(..., stream_mode="messages")`
5. 只保留 `meta["langgraph_node"] == "agent"` 的 chunk
6. 累加文本；`persist=True` 时写 `messages` 表
7. 生成器结束前完整落库（异常时按现有语义决定是否半途写）

三个调用点只保留：**造输入消息 → 消费文本流**。危机回合保持原路径（直连模型 + 注入），只共用闸门，不强行并入——它的流不是主图的流。

**验收标准**：

- `api/chat.py` 中 `graph.stream` 出现次数为 0；`core/companion.py` 中同样为 0。
- 测试可注入假 graph adapter（两个 adapter：真 LangGraph、内存假图），`test_companion_engine.py` 不再伪造 chunk/meta 二元组。
- 现有全部测试通过；聊天流、唤醒、危机回合、主动开口四条链路实机各走一次，文本增量顺序与 SSE 行为不变。

**风险与回滚**：四条调用点的落库语义有细微差异（危机回合注入、wake 的首条消息），实施前先列出差异表；一旦行为不一致，回退 `turn.py` 并恢复内联，单文件改动不影响数据。

---

### 候选 2（Strong）· settings 键单一归属 + 巡逻旗标具名化

**涉及文件**：

- `src/down_note/core/companion.py:30-32`（`ENABLED_KEY` / `TIER_KEY`）、`:124-155`（`_skipReason` 旗标）、`:192-196`（`patrol(ignoreTiming=…)`）
- `src/down_note/api/settings.py:23-24`（`COMPANION_ENABLED_KEY` 同字面值重复定义）、`:114`、`:138`（entryReply / persona 已用 import 风格）
- `src/down_note/api/companion.py:29-36`（`/api/companion/patrol` 生产端点）

**现状**：（a）`"companion_enabled"` 字面值两处定义，改键名要改两处且不报错，测试引用 `companion.ENABLED_KEY` 时 api 侧改动不会失败；（b）`ignoreTiming` / `ignoreNextAt` 两个布尔旗标把开发自测口子编码进生产 interface，`_skipReason` 内部分支随旗标组合翻倍。

**方案**：

- 键归属：core 模块拥有常量，api 只 `import`——与 `entryReply.ENABLED_KEY`、`persona.PERSONA_ENABLED_KEY` 对齐。
- 旗标改具名豁免集合：

```python
def patrol(now=None, skipKinds: set[str] | None = None):
    """skipKinds 取值 {"grace", "nextAt"}：grace=跳过启动缓冲，nextAt=跳过未到点；
    仅用于开发自测，生产调用不传。窗口、上限、让路、退避永远不被豁免。"""
```

`_skipReason` 内改为 `if "grace" not in skipKinds` / `if "nextAt" not in skipKinds` 的具名判断，删除布尔真值表分支；开发自测的默认豁免集合收成 `DEV_SKIP_KINDS = frozenset({"grace", "nextAt"})`，由 `api/companion.py` 引用。

**验收标准**：

- `grep -rn '"companion_enabled"' src/` 只命中一处（常量定义）。
- `grep -rn 'ignoreTiming\|ignoreNextAt'` 为 0。
- 测试覆盖 `skipKinds` 的三种组合（无 / timing / 两者），行为与旧旗标一致。
- 实机验证主动陪伴开关双向生效（对齐 2026-10-12 修复"开关关不掉"的回归口径）。

**风险**：低。键收口是纯去重；旗标重塑只动开发自测路径，生产调用不传参即旧行为。

---

### 候选 3（Strong）· db seam 收口

**涉及文件**：

- `src/down_note/api/chat.py:156`、`src/down_note/core/companion.py:257`（`db.get(models.ChatSession, sessionId)`）
- `src/down_note/api/entries.py:94-98`（`entryToRead` docstring 要求调用方保证"在会话内且 mood 可加载"）
- `src/down_note/db/database.py:59`（`expire_on_commit=False`，响应组装在会话外）
- `src/down_note/api/diaries.py:10`（横向 import entries 的读模型）

**现状**：`models` 包定义了约 50 个访问函数作为门面，但 `db.get(...)` 留了后门——同一个 seam 上"走门面"与"穿门面"并存，审查者无法靠 `models.*` 覆盖面推断数据访问面。`entryToRead` 把 SQLAlchemy 的 DetachedInstanceError 风险转嫁给每个调用点的纪律。

**方案**：

- 给 models 补充漏掉的访问函数（如 `getSessionById(db, sessionId)`），api / core 内 `db.get` 降为 0。
- `entryToRead` 改为自取数据：接收 `entryId` + `db`，内部完成带 mood 的查询与组装；或由 models 提供 `loadEntryWithMood(db, entryId)` 返回已 eager-load 的对象。二选一，以"调用方不再需要知道 ORM 生命周期"为验收。
- 实测踩坑：`loadEntryWithMood` 必须带 `populate_existing=True`——改正文后 `clearMood` 删掉旧心情，身份映射里的旧对象仍挂着关系，不加会读到过期数据（`test_updateEntryOnlyTodayAllowed` 会失败）。
- `diaries.py` 的横向 import 随读模型上移（放到 `api/readModels.py` 或各域自持），不作为本批硬指标。

**验收标准**：

- `grep -rn 'db\.get(' src/down_note/api src/down_note/core` 为 0。
- 任何响应组装函数都不再要求调用方传入"会话内对象"。
- 现有测试通过；日记列表、日页、聊天会话读取实机各走一次（重点关注 lazy load 报错）。

**风险**：中低。ORM 查询语义改动集中在 models 层；若出现 `DetachedInstanceError`，回退单个函数即可。

---

### 候选 4（Worth exploring）· 会话生命周期收口

**涉及文件**：

- `src/down_note/agent/context.py:107-155`（`_promptBlocks` 模块级 dict + prime/forget/refresh 四函数）
- `src/down_note/api/chat.py:121`（`primePromptBlocks`）、`:235-247`（`deleteChatSession` 人肉调 `forgetPromptBlocks`）
- `src/down_note/core/companion.py:176`（`refreshSystemPrompt`）

**现状**：缓存本身是必要复杂度（稳态不重建，保 prefix cache），但删除一个会话的正确性散在三处：`delete_thread`、`deleteSessionMessages` / `deleteChatSession`、`forgetPromptBlocks`；未来任何新删除入口忘一步就产生脏快照。缓存以四个自由函数 + 一个模块级 dict 摊开，无 owner。

**方案**：新增 `src/down_note/agent/session.py`：

```python
def dropSession(sessionId: str) -> None:
    """删除会话的全部痕迹，幂等：checkpoint 线程 → messages → chatSession → 提示词快照。"""
```

- 顺序固定为：checkpoint 线程 → 消息 → 会话行 → 快照失效（先删引用再删实体会让中途失败可重试，幂等）。
- `_promptBlocks` 缓存仍由 `context.py` 实现，`session.py` 是唯一删除入口并调用 `forgetPromptBlocks`——搬家收益低于它带来的模块缠绕，按 YAGNI 留在原处。
- 本批只做删除侧；`createSession` 暂无第二个调用语义需要统一，等真实需求出现再收。
- `api/chat.py` 的删除端点只调 `dropSession(sessionId)` 一个函数。

**验收标准**：

- 删除端点内不再直接出现 `delete_thread` / `deleteChatSession` / `forgetPromptBlocks`。
- 测试用两个 adapter（真 SQLite + 内存 fake）验证：删除后 checkpoint、messages、chatSession、快照四处均无残留；重复调用不报错。
- 实机会话删除 + 立即唤醒 + 主动开口各一次，确认无旧提示词残留。

**风险**：中。删除顺序与幂等性是本候选的核心；先补测试再改实现（TDD）。

---

### 候选 5（Worth exploring）· 主动开口链路归位

**涉及文件**：

- `src/down_note/scheduler.py:31-137`（`consolidatePastDays` 等四个任务的**实现**住在这里）、`:165-171`（注册 `companion.patrol`，但实现不住这里）
- `src/down_note/core/analysis.py:154-158`（尾部 try/except 旁路调用 `entryReply.generateEntryReply`）
- 链路其余站：`core/signals.py` → `core/events.py` → `api/notify.py` → `frontend` 通知栈

**现状**：`scheduler.py` 身份分裂——四个任务实现住自己这，`patrol` 实现住 core，归类标准不一致。理解"它为什么此刻开口/没开口"需要串联调度注册、settings JSON 状态机、信号判据、activity 上报四站。"分析完成 → 可能有回应"的因果链藏在 `analysis` 函数体末尾的 try/except 里。

**方案**（两项，分别独立验收）：

1. **scheduler 降为纯注册表**：四个任务的实现移入 `core/tasks/`（每个任务一个 module，判定 + 实现同处），`scheduler.py` 只剩 `add_job` 注册与启动缓冲。这是"浅得其所"——组合根本来就该浅。
2. **因果链显式化**：不做新事件机制（单一消费方，不满足"两个 adapter 才是真 seam"）。把"分析 → 回应"编排抽到一处显式函数（如 `core/pipeline.py::analyzeEntry(entryId)`，内部顺序调用 `analyze` 与 `generateEntryReply`），`analysis.py` 不再在尾部旁路调 entryReply。

**验收标准**：

- `scheduler.py` 内不再有任务实现代码；测试可直接调用任务函数，不经过 APScheduler。
- `analysis.py` 内不再 import `entryReply`；"分析 → 回应"的调用链在 `pipeline.py` 一屏可见。
- 「纯程序判定、模型只说内容」的决策不变——判定不得挪进模型调用（05 模块文档约束）。
- 日整合、补扫、记忆沉淀、主动巡检四条后台链路实机各跑一次。

**风险**：中。任务实现搬家只动 import 与注册；编排改动要保证"回应失败不影响分析成功"的现有语义（try/except 逻辑移入 pipeline，语义保持）。

---

### 候选 6（已完成）· agent/tools 按域合并

**现状**：`agent/tools/` 下 10 个约 25 行的实现文件 + 4 个纯 re-export 的 `__init__.py`。看 `addMemory` 实现要穿过三层跳转；工具 docstring 是给模型看的 prompt 资产，"Agent 有哪些工具、口径是什么"的全局视图被打散。

**deletion test**：按域合并（`tools/memory.py` 约 90 行）→ interface 不变、跳转少两层，桶文件的全部代码就是搬家成本本身。结论成立。

**为什么曾挂起**：与 `docx/v0.1.2/modules/00-结构重构.md` 的"一工具一文件"决策正面冲突。**2026-10-20 已修订**该文档（新增「后续修订」一节，改为按域一文件，工具 docstring 逐字保留），本候选现在可以实施。

**若启动，验收标准**：工具数量与 docstring 口径不变；`tools/__init__.py` 只导出工具列表；prompt 快照内容逐字不变；测试全过。

---

### 候选 7（Speculative）· 前端壳 adapter 独立 + 通知 pending 合一

**涉及文件**：

- `frontend/src/stores/appState.ts:13-46`（壳检测 / 窗口动作 / 标题栏同步）、`:50-148`（主题、视图、降级、记忆缓存、pendingSessionId）
- `frontend/src/stores/notify.ts:15-38`（模块级 `pending` + 10 分钟 TTL）
- `frontend/src/components/chat/ChatPanel.vue:149-160`（watch 消费并清空）

**现状**：`appState.ts` 装了五类不相关概念，壳 adapter 是纯基础设施；"点通知回到会话"需要三个文件接力，两段命名几乎相同的 pending 状态语义各半。

**方案**：

- 壳 adapter（`isTauri` / `readPywebviewApi` / `windowAction` / `bindTitlebarSync`）抽到 `frontend/src/stores/shell.ts`。
- 通知 pending 合一：`appState.pendingSession = { sessionId, requestedAt }`；`notify.ts` 不再持有自己的 `pending`，TTL 判定在写入或消费处只做一次（`requestOpenSession(sessionId, ttlMs)`）。

**验收标准**：`grep -rn 'pending' frontend/src` 只出现一处状态定义；通知点击 → 打开会话在 Tauri 与 dev 浏览器各手测一次；壳窗口动作（最小化 / 最大化 / 关闭）回归。

**风险**：低，但属前端手测范畴，放在最后。

## 五、实施批次

| 批次 | 内容 | 前置 | 交付物 |
|---|---|---|---|
| A | 候选 1 + 候选 2 | 无 | `agent/turn.py`；companion 常量收口；测试改造 |
| B | 候选 3 + 候选 4 | A（候选 4 依赖回合 module 的建图入口） | models 补漏；`agent/session.py`；删除端点收口 |
| C | 候选 5 | A | `core/tasks/` 归位；`core/pipeline.py` 显式编排 |
| D | 候选 7 | 无（可并行） | `stores/shell.ts`；pending 合一 |
| 挂起 | 候选 6 | 先修订 `00-结构重构.md` | — |

每批流程：先补测试（TDD）→ 落实现 → `uv run pytest` 全过 → 实机走对应链路 → 回填本文件进度。不改产品行为，不需要版本号，不需要发版。

## 六、进度

- [x] 批次 A · 候选 1 主图回合深 module（2026-10-20 落盘：`agent/turn.py::runAgentTurn`，三处流循环归位；新增 `tests/test_turn.py` 3 项；155 tests passed；四条链路实机待走）
- [x] 批次 A · 候选 2 settings 键收口 + 旗标具名化（2026-10-20 落盘：`DEV_SKIP_KINDS` + `skipKinds`；152 tests passed；托盘「试一次开口」实机待点一次）
- [x] 批次 B · 候选 3 db seam 收口（2026-10-20 落盘：`getSessionById` + `loadEntryWithMood`；api/core 内 `db.get` 归零；踩坑：`populate_existing=True`）
- [x] 批次 B · 候选 4 会话生命周期收口（2026-10-20 落盘：`agent/session.py::dropSession`；新增快照清理测试；156 tests passed）
- [x] 批次 C · 候选 5 主动开口链路归位（2026-10-20 落盘：任务实现迁入 `core/tasks.py`、`scheduler.py` 只剩注册；`core/pipeline.py::analyzeAndReply` 显式因果；新增 `tests/test_pipeline.py` 3 项；159 tests passed）
- [x] 批次 D · 候选 7 前端壳 adapter 与 pending 合一（2026-10-20 落盘：`stores/shell.ts` 承接壳 adapter；`pendingSession` 单状态 + `mark/take`；`npm run build` 通过；159 tests passed）
- [x] 候选 6 · agent/tools 按域合并（2026-10-20 落盘：`clock/diary/memory/session` 四文件；10 个工具 docstring 逐字比对零差异；159 tests passed）
