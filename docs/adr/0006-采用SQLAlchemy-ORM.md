# 采用 SQLAlchemy ORM

初版数据层用标准库 sqlite3 + 手写 SQL，理由是表少查询简单。2026-10-05 项目主理人决议改用 ORM：选定 SQLAlchemy 2.0 声明式映射——同步会话模式与本项目 FastAPI 同步端点匹配、生态成熟；不选 SQLModel（对 pydantic/SQLAlchemy 版本耦合深、成熟度不足）。数据访问函数签名保持稳定，调用方仅从行取值改为属性访问。列名与 ORM 属性沿用 snake_case（编码规范的数据库约定例外），API 层 JSON 仍转驼峰。代价：引入 SQLAlchemy 依赖、需熟悉 2.0 风格；测试环境通过 `database.resetEngine()` 在切换数据目录后重置全局引擎，防止跨用例串库。
