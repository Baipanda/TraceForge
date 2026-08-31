# TraceForge Agent Memory

这是 Agent 工作区的长期约定入口，不存放密钥。

TraceForge 现在已经有真实的 memory 子系统，不只是把这份文档读进 prompt。
这份文件负责“长期原则”和“可人工维护的默认事实”，代码层负责会话记忆、长期事实和检索。

## 当前项目状态

- Zulip 是当前主要交互入口。
- Jarvis 通过本机进程版 Zulip bridge 接入 TraceForge。
- TraceForge API 通过 DeepSeek 生成回复。
- Todo、RAG、MCP 和 Gateway/Runtime 编排仍在逐步建设。
- 当前已加入本地身份种子：`Neymar / neymar@traceforge.local`、`Peter / peter@traceforge.local`、`Gwen / gwen@traceforge.local`，用于 Zulip 用户名和业务身份的映射演示。

## 记忆边界

- Zulip 原始 Topic 历史由 Zulip 保存。
- TraceForge 只保存经过筛选的摘要、事实、任务关系和运行审计。
- 不把未经确认的模型推断写入长期记忆。

## 记忆分层

- Session memory：当前 Topic / 私聊会话的压缩摘要。
- Working memory：正在处理的上下文、待办、身份映射。
- Long-term memory：稳定事实、偏好、决策和约定。
- RAG memory：以后接独立检索系统时再接入。

## 当前实现

- SQLite 里已经有 `traceforge_memory_entries`。
- Gateway 会在每次请求前检索相关记忆，并把结果交给 Harness。
- 每次请求结束后，TraceForge 会写回会话摘要和身份事实。
