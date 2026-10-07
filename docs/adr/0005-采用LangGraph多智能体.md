# 采用 LangGraph 构建多智能体

Agent 层需要多智能体派发（主智能体 + 回顾/记忆管理子智能体）、工具调用与会话状态持久化，LangGraph 现成提供这三样，手写循环等于重造轮子；其消息模型（SystemMessage/HumanMessage/AIMessage）与 OpenAI 兼容端点契合，langchain-openai 同时统一了分析、危机复判与智能体的全部模型调用（一套三件套配置、一套错误归类）。设计约定：短期记忆独立库表存放，checkpoint 只做图状态恢复而非记忆载体；会话消息严格追加（SystemMessage 定、HumanMessage/AIMessage 逐轮加尾）以保 prefix cache；v0.1.0 不做会话压缩、不做上下文超限处理（已知限度）。代价：引入 langchain 依赖族（体积大、版本迭代快），团队需熟悉其抽象。
