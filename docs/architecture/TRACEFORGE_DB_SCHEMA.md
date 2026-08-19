# TraceForge 本地数据库

第一版先用 SQLite 跑通第一条链路，后续可以平移到 PostgreSQL。

## `traceforge_todos`

存 Todo 主表。

创建 Todo 的产品级必填项是：

- `title`: 标题
- `proposer_name` 或 `proposer_email`: 发布者，来自 Zulip 消息发送人
- `assignee_name` 或 `assignee_email`: 执行者，来自用户指令或 `workspace/people.json` 身份解析

其余字段由 TraceForge 默认填充或允许为空。

- `id`: Todo ID
- `title`: 标题
- `description`: 描述/原始请求
- `status`: `open` / `in_progress` / `done` / `canceled`
- `priority`: 优先级
- `workspace_id`: 归属工作区
- `channel_name`: 来源频道名
- `topic`: 来源 Topic
- `proposer_name`: 发起人名称
- `proposer_email`: 发起人邮箱
- `assignee_name`: 负责人名称
- `assignee_email`: 负责人邮箱
- `source_message_id`: Zulip 原消息 ID
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `completed_at`: 完成时间
- `deleted_at`: 删除时间

## `traceforge_todo_events`

存 Todo 变更历史。

- `id`: 事件 ID
- `todo_id`: 对应 Todo
- `action`: `create` / `update` / `delete`
- `actor_name`: 操作者名称
- `actor_email`: 操作者邮箱
- `detail_json`: 结构化变更摘要
- `created_at`: 事件时间

## `traceforge_sessions`

存 workspace/topic 级会话锚点。

- `session_key`: 会话键
- `workspace_id`: 工作区
- `channel_name`: 频道名
- `topic`: Topic
- `created_at`: 创建时间
- `updated_at`: 更新时间
