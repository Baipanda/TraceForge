---
name: topic-summary
description: 当用户要求总结当前 Zulip Topic、提炼结论或识别风险时使用
allowed-tools:
  - zulip.fetch_topic
  - rag.search
  - todo.create
  - zulip.reply
---

# Topic 总结

## 处理流程

1. 获取当前 Topic 的消息上下文。
2. 区分事实、讨论意见、未决问题、决定和风险。
3. 必要时检索 TraceForge 知识库，标记外部资料来源。
4. 只在用户明确要求或 Skill 规则允许时创建 Todo。
5. 将总结、结论、风险和待办分段回复到原 Topic。

## 约束

- 不把推测写成已经确认的结论。
- 总结必须保留来源 Topic 和关键证据。
