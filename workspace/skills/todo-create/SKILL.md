---
name: todo-create
description: 当用户要求创建、发布或记录 Todo 时使用
allowed-tools:
  - people.resolve
  - todo.create
  - zulip.reply
---

# 创建 Todo

## 处理流程

1. 从用户请求中提取任务标题、负责人、截止时间、优先级和来源 Topic。
2. 负责人不明确时调用 `people.resolve`；解析失败就向用户澄清。
3. 必要字段完整后调用 `todo.create`。
4. 只有工具返回成功，才能回复“已创建”。
5. 将 Todo ID、负责人、来源 Topic 和执行结果回复到原消息所在 Topic。

## 约束

- 不要根据聊天内容假装 Todo 已经写入数据库。
- 不要把普通聊天中的“以后记一下”直接当成创建操作，必要时确认。
