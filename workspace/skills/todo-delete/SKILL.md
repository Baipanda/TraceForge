---
name: todo-delete
description: 当用户要求删除、删掉、去掉或移除 Todo 时使用
allowed-tools:
  - people.resolve
  - todo.list
  - todo.delete
  - zulip.reply
---

# 删除 Todo

## 处理流程

1. 先定位目标 Todo（**不要**让用户提供数据库 ID）：
   - 用标题关键词 `match_title`（可用关键片段；允许轻微错别字）
   - 可选 `match_assignee_name` / `match_assignee_email`
   - Topic 对话中默认带上当前 Topic；私聊若用户点了 Topic 也要传
2. 条件不够清晰或匹配多条时，先 `todo.list` 展示候选，请用户补标题后再删。
3. 调用 `todo.delete`（传 `match_*` / `topic`，不要向用户念内部 ID）。
4. **直接使用工具返回的 `reply_text`**（成功时为「已删除 Todo」表格）。
5. 若用户标题有错别字，仍应尝试 `todo.delete`；不要只口头答应却不调工具。

## 约束

- 未准确定位前不要删除；匹配多条时禁止猜测删错一条。
- 不要把内部 ID 念给用户听。
- 「关掉 / 完成」不是删除 → 用 `todo-update`；只有明确删除/删掉/去掉才走本 Skill。
