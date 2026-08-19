# TraceForge Tool 约定

TraceForge 的 Tool 有两种来源：

1. Local Tool：由 TraceForge 自己实现，访问自己的数据库、Zulip API 或本地资源。
2. MCP Tool：由外部 MCP Server 提供，通过 MCP Client 接入。

Agent 只使用逻辑工具名，不关心工具的具体实现来源。

## 当前已落地的工具

- `people.resolve`
- `todo.create`
- `todo.list`
- `todo.update`
- `todo.delete`
- `todo.summary`

## 工具结果

每个工具都应该返回：

- `ok`：是否成功
- `data`：结构化结果
- `error`：失败原因
- `evidence`：可以展示或审计的证据

## 安全要求

- 不允许把 API Key、密码、Token 放进 prompt、ToolResult 或 Zulip 回复。
- 不允许绕过 Tool 直接执行任意 SQL 或 Shell。
- 写操作应支持幂等键或重复执行保护。
