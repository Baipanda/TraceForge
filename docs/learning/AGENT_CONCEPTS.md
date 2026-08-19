# TraceForge Agent 学习笔记

这份文档面向刚开始做 Agent 工程的开发者。它把 TraceForge 的实现和 OpenClaw / `openclaw-zulip-bridge` 的设计对应起来。

## 1. 先建立总图

一个可落地的 Agent 通常不是“一个大模型接口”，而是一条执行链：

```text
外部消息
  -> Adapter
  -> Context
  -> Session
  -> Gateway
  -> Agent Runtime
  -> Harness / Skill
  -> LLM
  -> Tool
  -> Application / Repository
  -> Reply
```

TraceForge 当前已经接通了：

```text
Zulip
  -> Zulip Bridge
  -> ZulipContextBuilder
  -> SessionKeyResolver
  -> WorkspaceGateway
  -> Todo Application
  -> SQLite
  -> Zulip 回复
```

Todo 仍然优先走确定性 Application，这是有意的设计。复杂聊天理解可以使用模型，但 Todo 写入、权限、幂等和字段校验不能只依赖模型。

## 2. OpenClaw 的参考价值

### `openclaw-zulip-bridge` 是 Channel Plugin

它不是一个独立的“Zulip 智能理解模型”。它主要负责：

- 轮询 Zulip 事件队列
- 处理 queue 持久化、过期重连和去重
- 解析私聊、stream、Topic 和 mention
- 将 Zulip 消息转换成 OpenClaw 可消费的 inbound event
- 把 Agent 回复投递回原 stream、Topic 或私聊
- 处理 Markdown、分片、附件、reaction 和权限策略

### OpenClaw Runtime 负责 Agent 行为

OpenClaw 的强大来自多个部分配合：

```text
Channel Plugin
  + Gateway / Dispatcher
  + Session 路由
  + Workspace 文件
  + Skills
  + Memory
  + Tools
  + Agent Runtime
```

因此 TraceForge 不应该把所有能力堆到 bridge 中。Bridge 应该成为可靠的 Zulip Adapter；上下文构建、会话和 Agent 执行属于 TraceForge 自己的核心。

## 3. 常见 Agent 技术概念

### Context：本轮决策需要知道什么

Context 是模型或 Runtime 在当前请求中可见的信息集合。

对 Zulip Agent 来说，Context 至少包括：

- 当前消息文本
- 发送者 ID、邮箱、显示名
- 消息类型：stream 或 private
- stream、Topic
- 私聊参与者
- mention
- 当前会话的历史摘要
- 相关数据库事实
- 当前可用 Skill 和 Tool

Context 不是简单地把所有历史消息拼接起来。高质量 Context 应该有来源、范围和优先级。

TraceForge 的 `ZulipContextBuilder` 负责把渠道数据转换成结构化 Context；未来可以继续增加 Topic 历史和 RAG 结果。

### Session：哪些消息属于同一段持续对话

Session 不是“每个用户一个 Session”，也不是“每条消息一个 Session”。

当前 TraceForge 的规则：

```text
stream Topic:
zulip:<workspace>:stream:<stream_id>:topic:<topic>

private message:
zulip:<workspace>:dm:<participant_set_digest>
```

这样：

- 同一 Topic 的多人讨论共享上下文
- 同一私聊参与者集合共享上下文
- 不同 Topic 互不污染
- 用户在不同 Topic 中可以有不同任务状态

OpenClaw 值得借鉴的地方是：Session Key 必须稳定，且要参与 Agent 路由和历史加载。

### Memory：应该长期记住什么

Memory 不是聊天记录数据库。

更合理的区分是：

```text
原始消息历史：Zulip 保存
短期会话上下文：Session / Context Store
长期事实：Memory
业务数据：Todo / Document / Finding 表
运行审计：Agent Run / Tool Call
```

例如：

- “Neymar 对应 `neymar@traceforge.local`”可以成为身份事实
- “这个 Topic 的最终决定是采用 JWT”可以成为 Topic 摘要
- “模型曾经猜测某段代码有风险”不能直接写入长期 Memory

OpenClaw 的 `MEMORY.md` 体现了人工维护的长期约定；TraceForge 后续应增加带来源、时间和置信度的结构化 Memory。

### Intent Recognition：用户想做什么

意图识别的结果不应该只是一个字符串，而应该是结构化命令：

```json
{
  "intent": "todo.create",
  "title": "检查认证模块",
  "assignee": "Neymar",
  "topic": "安全排查",
  "confidence": 0.96
}
```

当前 TraceForge 使用规则解析 Todo，这是第一阶段的优点：

- 快
- 可测试
- 不依赖模型
- 不容易产生虚假写入

后续可以让 LLM 负责提取结构化意图，但必须由 Application 再次校验。

推荐的执行方式：

```text
用户文本
  -> LLM / Rule 提取 Command
  -> Schema 校验
  -> 权限校验
  -> Application 执行
```

### Skill：告诉 Agent 如何完成一类任务

Skill 不是 Tool。

```text
Skill = 流程、约束、选择工具的说明
Tool  = 一个可执行动作
```

例如 `todo-create/SKILL.md` 可以规定：

1. 解析标题和执行者
2. 必要时调用 `people.resolve`
3. 调用 `todo.create`
4. 只有成功后才能回复“已创建”

而 `todo.create` 只是实际写入数据库的动作。

OpenClaw 的 Skill 设计值得参考：它把行为流程写在 Workspace，而不是全部硬编码进 Runtime。

### Harness：组装工作环境

Harness 负责把这些东西组装成模型输入：

```text
身份规则
+ 工作区约定
+ 选中的 Skill
+ 当前 Context
+ Memory
+ Tool Schema
```

TraceForge 当前的 `PromptHarness` 已经能加载 `AGENTS.md`、`IDENTITY.md`、`TOOLS.md`、`MEMORY.md` 和匹配的 Skill。
HTTP 主链路已经统一进入 AgentRuntime，Todo 也由 Runtime 选择 Tool，
但最终事务仍然由确定性 Application 保证。

### Runtime：执行循环

Runtime 不是一个普通的业务函数，它负责一轮 Agent Run：

```text
创建 Run
  -> 组装 Prompt
  -> 调用模型
  -> 解析 Tool Call
  -> 执行 Tool
  -> 把 ToolResult 放回上下文
  -> 再次调用模型
  -> 达到终止条件
```

TraceForge 当前的 `AgentRuntime` 第一版已经接通，具备：

- `AgentRequest`
- `AgentRun`
- `RunStep`
- `PromptBundle`
- Tool Registry 接口
- 模型 Tool Call 解析
- Tool 执行结果回填
- 最大步数限制
- Agent Run evidence

下一步需要增加更可靠的 Tool Call 校验、权限策略和运行轨迹持久化。

## 4. TraceForge 当前值得保留的设计

### 确定性业务优先

Todo 创建不是让模型直接写数据库，而是：

```text
Intent
  -> Tool
  -> TodoWorkflow
  -> Repository
```

这比“模型直接生成 SQL”更适合安全和招聘作品展示。

### Tool 与 Application 分离

Tool 是 Agent 的能力边界，Application 是确定性业务流程。这样未来接 MCP 时，MCP Tool 也可以进入同一个 Tool Registry。

### Evidence-first

每次处理都会保留：

- intent
- tool name
- todo 数据
- session key
- context

这为后续 Agent Run 审计、评估和调试打基础。

## 5. 下一步学习和实现顺序

建议按以下顺序推进：

1. 为 Zulip Context 增加 Topic 历史读取
2. 给 Session 增加短期消息摘要
3. 让 `PromptHarness` 只加载匹配的 Skill
4. 为 DeepSeek Tool Calling 增加更严格的结构化校验
5. 将 Topic 历史和 Memory 接入 `AgentRuntime`
6. 增加 `zulip.fetch_topic`
7. 增加 RAG：Topic -> 文档/代码/安全知识检索
8. 增加 Agent Run 和 Tool Call 持久化
9. 增加评估集，测试意图识别、工具选择和回复准确率

最终 TraceForge 的核心竞争力应该是：

```text
Zulip 团队上下文
  + 可解释的 Agent Runtime
  + 可审计的工具调用
  + 研发/安全领域 RAG
  + 确定性业务闭环
```
