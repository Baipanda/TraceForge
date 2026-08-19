# OpenClaw 相关数据库表清单

这份记录只收**表名与作用**，不收数据。用途是 TraceForge 后续迁移/重建 schema 时，有一份最小可依赖的表 inventory。

## 已确认表

### `todos`
主任务表。

已从本机脚本和文档中确认的字段/用法包括：

- `id`
- `title`
- `description`
- `proposer_id`
- `assignee_id`
- `zulip_stream`
- `zulip_topic`
- `source_message_id`
- `priority`
- `subtree_id`
- `parent_id`
- `image_paths`
- `main_force_ids`
- `process_manager_ids`
- `technical_advisor_ids`
- `backup_force_ids`
- `watcher_ids`
- `proportion`
- `status`
- `completed_at`
- `created_at`
- `updated_at`
- `deleted_at`

### `todo_progress_history`
Todo 的进展历史表。

已确认字段：

- `todo_id`
- `content`
- `recorded_by`
- `recorded_at`

注意：当前记忆里明确要求“今日同步进展”要查这张表，不看 `todos.progress_prompt`。

### `subtrees`
子树/模块表。

已确认字段：

- `id`
- `name`
- `parent_id`
- `level`

### `people`
人员主表。

已确认用途：

- canonical person 记录
- 和 `person_aliases` 联合做别名解析

### `person_aliases`
人员别名表。

已确认用途：

- 别名 -> person 映射
- `todo-cli.js` 通过它解析 proposer / assignee / role 字段

### `projects`
项目维度表。

当前只确认它是 schema inventory 的一部分，具体字段后续再用 live schema 补齐。

## 目前没法确定是否存在的表

以下名字在当前记忆和脚本中**没有形成完整证据链**，迁移前需要再查 live schema：

- `identity_links`
- 其他 Zulip 相关扩展表

## 备注

已确认的表和用途主要来自：

- `~/.openclaw/workspace/MEMORY.md`
- `~/.openclaw/workspace/scripts/db-state-query.js`
- `~/.openclaw/workspace/scripts/todo-cli.js`
- `~/.openclaw/workspace/scripts/database-query-prefetch.js`

如果要真正重建数据库，下一步应该直接对 live Postgres 跑 schema 查询，再把每张表的列级信息补全。
