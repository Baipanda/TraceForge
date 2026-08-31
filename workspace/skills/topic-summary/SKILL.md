---
name: topic-summary
description: 当用户要求总结当前 Zulip Topic、提炼结论或识别风险时使用
allowed-tools:
  - topic.summarize
  - zulip.fetch_topic
  - todo.create
  - zulip.reply
---

# Topic 总结

## 处理流程

1. 调用 `topic.summarize`（或 `zulip.fetch_topic`）：通过 Zulip API 拉取**整个 Topic** 的消息，并附带本 Topic Todo 进展。
2. **直接使用工具返回的 `reply_text`**，不要改写 Markdown 结构。
3. 仅当用户明确要求「据此创建 Todo」时，再调用 `todo.create`。

## 约束

- 不把推测写成已经确认的结论（由 Application 层 LLM 规则约束）。
- 私聊且未指定 Topic 时，工具会提示缺位置信息。
- 本期不读写 Memory / RAG。
- 不要向用户展示内部数据库 ID。
