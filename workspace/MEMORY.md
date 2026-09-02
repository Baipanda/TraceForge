# TraceForge Agent Memory

这是 Agent 工作区的**精选核心**入口：极短原则与索引，每次自动注入（有长度预算）。

情景细节不写在这里，写到 `memory/` 下，靠 `memory.search` / `memory.get` 召回。

## 分层

| 层 | 位置 | 注入 |
|----|------|------|
| 指令 | `AGENTS.md` | 每次 |
| 精选核心 | `MEMORY.md`（本文件） | 每次 |
| 个人习惯 | `memory/preferences/<person_id>.md` | 每次，仅当前发言人 |
| 情景日记 | `memory/YYYY-MM-DD.md` | 不自动注入，搜索 |
| 决策/Todo 摘要 | `memory/DECISION.md` | 不自动注入，搜索 |
| 工作记忆 | session JSONL | 近 ~20000 tokens 滑动窗 |

## 写入约定

- 用户说「以后 / 之后 / 记住 / 下次请…」→ 工具 `memory.remember` → preference 文件。
- 重要决策 / Topic 结论 / 关键 Todo 变更 → `memory/DECISION.md`（后续由 flush / topic_summary / todo 挂钩自动写）。
- 当天观察与会话摘记 → `memory/YYYY-MM-DD.md`。

## 索引

Markdown 为权威正文；SQLite FTS（`memory_md_*`）为派生索引，可重建。

## 当前产品事实

- Zulip 是主要交互入口；Jarvis 经 bridge 接入 TraceForge。
- Workspace Person：`person_id` + Zulip binding；Todo / Preference 按人隔离。
