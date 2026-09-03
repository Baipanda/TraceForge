# workspace_shared

跨 Agent 共享知识库（规范、文档、FAQ）。

- **不是**第三个 Agent，没有独立 session / 人格
- 各 Agent workspace 通过只读方式引用这里的内容（后续 knowledge 工具）
- 人格、skills、行为边界仍放在各自的 `workspace` / `workspace-<id>`
