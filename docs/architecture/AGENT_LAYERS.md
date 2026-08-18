# TraceForge Agent 分层

TraceForge 借鉴 OpenClaw 的 Workspace 设计，但不把 Gateway、Agent Runtime、Harness 和业务逻辑揉成一个运行时。

代码目录上，`runtime`、`harness`、`skill_loader` 放在 `src/traceforge/agent/`。它们共同组成 Agent Engine。

`ToolRegistry` 放在 `src/traceforge/tools/`。原因是工具系统要同时承载本地工具和未来 MCP 工具，它应该被 Agent Runtime 调用，而不应该反过来依赖 Agent。

## 调用方向

```text
External Adapter
  -> Gateway
  -> AgentRuntime
  -> Harness
  -> LLM
  -> ToolRegistry
  -> Tool
  -> Application / Domain / Infrastructure
```

### Gateway

Gateway 是统一入口和路由层，不负责具体业务。

职责：

- 接收 `WorkspaceEvent`
- 构造 `AgentRequest`
- 计算 session key
- 做入口级权限和幂等检查
- 路由到普通 Application 用例或 AgentRuntime
- 接收最终响应并交给 Zulip/HTTP adapter

对应代码位置：`src/traceforge/gateway/`

### AgentRuntime

Runtime 是 Agent loop，不是业务服务。

职责：

- 创建 `AgentRun`
- 请求 Harness 组装模型输入
- 调用 LLM
- 解析最终回复或 ToolCall
- 调用 ToolRegistry
- 把 ToolResult 追加回上下文
- 在达到终止条件、最大步数或人工确认时结束

Runtime 不应该直接写数据库，也不应该知道 Zulip 的 HTTP 细节。

对应代码位置：`src/traceforge/agent/runtime.py`

### Harness

Harness 是 Agent 的运行环境组装器。

职责：

- 读取 `workspace/AGENTS.md`
- 读取 `workspace/IDENTITY.md`
- 读取 `workspace/TOOLS.md`
- 选择并加载匹配的 `SKILL.md`
- 加入 Topic、用户、历史消息和检索结果
- 生成 `PromptBundle`
- 过滤当前可用 Tool schema

Harness 不执行 Tool，也不决定数据库事务。

对应代码位置：`src/traceforge/agent/harness.py`

### Tool

Tool 是 Agent 能调用的动作边界。

本地 Tool 和 MCP Tool 都通过 `ToolRegistry` 暴露统一名称，例如：

```text
todo.create
todo.list
zulip.fetch_topic
github.search_code
security.scan
```

Tool 负责参数适配、调用外部能力、包装结构化结果；核心业务约束不能只写在 Skill 中。

对应代码位置：

- `src/traceforge/tools/registry.py`：统一工具注册表
- `src/traceforge/tools/models.py`：ToolCall / ToolResult 等工具契约
- 未来 `src/traceforge/tools/local/`：具体本地工具实现
- 未来 `src/traceforge/tools/mcp/`：MCP Client/Adapter

### Application / Domain

Application 不是所有 Agent 能力的必经层。

简单、灵活、可复用的能力可以走：

```text
Skill -> Runtime -> Tool -> Infrastructure
```

复杂、确定性强、涉及安全或事务的能力走：

```text
Skill -> Runtime -> Tool -> Application -> Domain/Repository
```

例如 Todo 创建必须由 Application/Domain 保证负责人存在、字段合法、幂等和事务一致性。
