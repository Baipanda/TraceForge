# TraceForge Agent Memory

这是 Agent 工作区的长期约定入口，不存放密钥。

## 当前项目状态

- Zulip 是当前主要交互入口。
- Jarvis 通过本机进程版 Zulip bridge 接入 TraceForge。
- TraceForge API 通过 DeepSeek 生成回复。
- Todo、RAG、MCP 和 Gateway/Runtime 编排仍在逐步建设。

## 记忆边界

- Zulip 原始 Topic 历史由 Zulip 保存。
- TraceForge 只保存经过筛选的摘要、事实、任务关系和运行审计。
- 不把未经确认的模型推断写入长期记忆。
