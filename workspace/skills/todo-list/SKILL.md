---
name: todo-list
description: 当用户要求查询、列出或查看 Todo 时使用
allowed-tools:
  - todo.list
  - todo.get
  - zulip.reply
---

# 查询 Todo

## 处理流程

1. 识别查询条件：负责人、状态、项目、Topic、时间范围或 Todo ID。
2. 调用 `todo.list` 或 `todo.get` 获取真实数据。
3. 使用工具返回的数据生成回复，不从历史聊天自行拼接 Todo。
4. 没有结果时明确说明查询条件和结果为空。

## 约束

- 查询操作不得修改 Todo。
- 不要展示用户无权访问的字段。
