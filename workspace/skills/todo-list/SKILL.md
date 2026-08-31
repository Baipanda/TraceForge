---
name: todo-list
description: 当用户要求查询、列出或查看 Todo 时使用
allowed-tools:
  - todo.list
  - people.resolve
  - zulip.reply
---

# 查询 Todo

## 处理流程

1. 从用户话里提取过滤条件（可组合）：执行者、状态、Topic、频道、优先级、标题关键词、发布者。
2. 若提到人名，先 `people.resolve`，再用邮箱调用 `todo.list`。
3. **直接使用工具返回的 `reply_text` 回复用户**，不要自行改写成带数据库 ID 的列表。
4. 若工具返回的是「汇总模式」（按 Topic / 执行者 / 状态计数），引导用户继续缩小范围后再查。
5. 没有结果时说明当前条件，并建议放宽或更换过滤项。

## 范围规则

- **在 Channel/Topic 里提问**：默认只查**当前 Topic**（用户若点名别的 Topic，以用户点名为准）。
- **与 Jarvis 私聊**：
  - 未点名 Topic 时：不限制 Topic（可查全部，结果过多会先汇总）。
  - **点名了 Topic 时必须按该 Topic 过滤**，例如「agent开发 下的全部 Todo」→ `topic=agent开发`。
  - 私聊「没有默认 Topic」≠「不能按 Topic 查询」。
- 不要向用户展示或索要 Todo 的数据库内部 ID。

## 组织树过滤

- 可按 `subtree_path` / `subtree_name` / `subtree_code` 过滤 Todo。
- 若用户问的是“某 subtree 下有哪些子节点 / 挂了哪些 Todo”，改用 `subtree-list` skill 的工具。

## 展示规则

- **列表明细**使用固定 Markdown **表格**（标题、状态、执行者、发布者、组织树、Topic、优先级、发布时间、完成时间）。
- **描述默认不查、不展示**；仅当用户明确要求查看描述时，调用 `todo.list` 并设 `include_description=true`。
- 禁止在回复里输出 `todo_xxxx` 这类内部 ID。
- 结果过多时先一级汇总，再按 Topic / 人筛选后出表。
- 按组织树筛选的能力后续再做；本期不要假装已支持 subtree 过滤。

## 可组合过滤示例

- 「Neymar 的 open Todo」
- 「football 下 Gwen 的待办」
- 「标题里带 复盘 的 Todo」
- 「私聊里查看全部，先按 Topic 汇总」→ 可传 `group_by=topic`

## 约束

- 查询不得修改 Todo。
- 过滤条件应映射到 `todo.list` 的参数；表结构将来加字段时，优先增加同名可选参数，保持组合查询可扩展。
