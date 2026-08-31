---
name: subtree-list
description: 查询组织树子节点，或查询某个 subtree 下挂载的 Todo
allowed-tools:
  - subtree.children
  - subtree.todos
  - todo.list
  - zulip.reply
---

# 组织树查询（subtree-list）

与 `todo-list` 对齐的查询 Skill。工具名保持语义清晰：`subtree.children` / `subtree.todos`。

## 场景

1. 「硬件下面有哪些子 subtree」→ `subtree.children`
2. 「某个 subtree 上挂了哪些 todo」→ `subtree.todos`

## 规则

- **直接使用工具返回的 `reply_text`**，不要改写表格结构。
- `subtree.children` 默认只列**直接子节点**；用户要“全部/所有子孙”时再设 `include_descendants=true`。
- `subtree.todos`：
  - Stream/Topic 对话：默认只看当前 Topic
  - 私聊：不限 Topic（除非用户点名 Topic）
  - 默认包含子孙节点上的 Todo
- 定位节点：可只给 **L3 名称**（如 `TraceForge Agent`），系统用 `parent_id` 向上补全 L1/L2 路径；也可用 `subtree_path` / `subtree_code`。
- 不要向用户展示内部数据库 ID。
