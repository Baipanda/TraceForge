---
name: todo-update
description: 当用户要求更新、修改、完成、关闭或改派 Todo 时使用
allowed-tools:
  - people.resolve
  - todo.list
  - todo.update
  - zulip.reply
---

# 更新 Todo

## 处理流程

1. 先定位目标 Todo（**不要**让用户提供数据库 ID）：
   - 用标题关键词 `match_title`（可用关键片段；允许轻微错别字）
   - 可选 `match_assignee_name` / `match_assignee_email`
   - Topic 对话中默认带上当前 Topic；私聊若用户点了 Topic 也要传
2. 条件不够清晰时，先 `todo.list` 展示候选，请用户补充后再改。
3. 调用 `todo.update`：
   - 定位：`match_*` / `topic`
   - 变更：`title` / `status` / `assignee_*` / `priority` / `description`
4. **直接使用工具返回的 `reply_text`**（成功时为 Markdown 表格，勿改写成卡片列表）。
5. 「完成 / 关掉 / 做完了 / 搞定」→ `status=done`；「进行中」→ `status=in_progress`。
6. 完成时间：
   - 用户**明确给了**时间点 → 传 `completed_at`（ISO-8601）
   - 用户说「现在 / 当前 Zulip 聊天时间」→ 传 `status=done`（可再次传），**不要**自己编时间；系统用这条 Zulip 消息时间覆盖
   - 已是 `done` 的 Todo **允许**改完成时间，不会锁定旧值
7. 自然语言也算更新意图，例如：「xxx 这个 todo 我已经完成了」「把 yyy 标成 done」——必须调用 `todo.update`，不要只口头确认。
8. 若用户标题有错别字，仍应尝试 `todo.update`；不要只口头答应「已更新」却不调工具。

## 展示与长度

- 与 `todo-list` 相同：不向用户展示内部 ID。
- 若匹配多条，工具会返回候选列表或汇总；继续缩小范围，禁止猜测改错一条。

## 约束

- 未准确定位前不要更新。
- 改派负责人时先 `people.resolve`。
- 不要把内部 ID 念给用户听。
