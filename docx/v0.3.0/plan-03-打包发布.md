# 03-打包发布 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 superpowers:executing-plans。步骤用 `- [ ]` 追踪。

**Goal:** 把 v0.3.0（日记回应 + 信号触发 + 记忆工具修复）打包成 `DownNote_0.3.0_x64-setup.exe` 并发布。

**所属版本：** v0.3.0 ｜ **前置依赖：** 00、01、02 全部完成且测试全绿（04 记忆修复已先行落盘）

## Global Constraints

- 运行 `uv run <命令>`；加依赖 `uv add`；推送与挂附件需用户同意。
- 版本号四处同步：`pyproject.toml`（version）、`frontend/src-tauri/tauri.conf.json`（version + 产物名）、`frontend/package.json`（version）、`README.md` 徽章；`uv.lock` 随版本号同步。
- 发布流程沿用 `uv run python scripts/build.py`（前端构建 → 后端 PyInstaller sidecar → Tauri NSIS）。

---

- [ ] **Step 1: 全量测试**

Run: `uv run pytest -q`（Expected: 全绿，含 01/02 新增用例与 04 既有 123 例，无回归）

- [ ] **Step 2: 版本号四处同步**——`pyproject.toml`、`tauri.conf.json`（version + 产物名）、`frontend/package.json`、`README.md` 徽章 0.2.0 → 0.3.0；`uv lock` 使 `uv.lock` 同步。

- [ ] **Step 3: README 功能一览**——补 v0.3.0 两项（日记回应、信号触发）+ 记忆工具修复说明；下载说明版本号更新为 0.3.0。

- [ ] **Step 4: 产包**

Run: `uv run python scripts/build.py` → 确认 `dist/DownNote_0.3.0_x64-setup.exe` 生成。

- [ ] **Step 5: 覆盖升级验证（用户实机）**——旧版本装 0.3.0：数据保留、写日记出回应、信号触发可验、历史条目无回应不报错；回填 v0.2.0 的 06 覆盖安装/干净机器验证遗留状态。

- [ ] **Step 6: Release 文案 + 推送**——主题「陪伴感深化」；撰写新功能用户视角描述与附件体积；推送与挂附件（经用户同意后执行）。

```bash
git add pyproject.toml uv.lock frontend/src-tauri/tauri.conf.json frontend/package.json README.md
git commit -m "发布：v0.3.0 版本号同步 + 功能一览更新"
```
