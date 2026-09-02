---
name: memory-remember
description: Persist personal preferences when the user asks to remember future habits.
tools:
  - memory.remember
  - memory.search
  - memory.get
  - people.resolve
---

# 记忆习惯

当用户表达长期习惯或偏好时使用，例如：

- 「以后用中文回复」
- 「之后记得我家乡在泰安」
- 「记住下次创建 Todo 默认指派给 Peter」

## 步骤

1. 确认当前发言人 `person_id`（来自事件上下文；不明时 `people.resolve`）。
2. 调用 `memory.remember`，写入简洁 note。
3. 简短确认已记住；不要把整份 preference 文件复读给用户。

情景决策、历史 Topic 结论用 `memory.search` / `memory.get`，不要写进 preference。
