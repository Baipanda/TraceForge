# TraceForge Agent 运行数据结构

第一版先使用 Python 类型表达运行契约，等 Todo Agent 跑通后再决定哪些字段需要持久化到 PostgreSQL。

## 请求

```text
AgentRequest
  event: WorkspaceEvent
  session_key: str
  request_id: str
  metadata: dict
```

`AgentRequest` 是 Gateway 交给 Runtime 的统一输入。它不包含 Zulip 专属逻辑，外部来源已经在 Adapter 层标准化。

## Harness 输出

```text
PromptBundle
  system_prompt: str
  messages: list
  tools: list[ToolSpec]
  skills: list[str]
  context_items: list[ContextItem]
```

`ContextItem` 必须包含来源，方便回答时引用证据，也方便后续审计。

## Tool 调用

```text
ToolCall
  call_id
  name
  arguments

ToolResult
  tool_name
  call_id
  ok
  data
  error
  evidence
```

无论本地 Tool 还是 MCP Tool，都转换成相同的 `ToolResult`。

## Agent Run

```text
AgentRun
  run_id
  request
  status
  steps[]
  final_text
  started_at
  finished_at
```

每个 `RunStep` 表示一次模型调用、Tool 调用、最终回复或错误。

## 未来数据库候选表

```text
agent_sessions
agent_runs
agent_run_steps
tool_calls
```

第一阶段不急着把所有模型上下文写入数据库。优先持久化：

- request_id / run_id
- session_key
- 状态和耗时
- Tool 调用名称、参数摘要和结果摘要
- 最终回复
- evidence

API Key、密码和完整敏感上下文不得写入运行审计。
