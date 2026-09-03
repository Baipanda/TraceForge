---
name: fs-workspace
description: 用户要读工作区文件、搜 workspace 内容时使用；调用 fs.read / fs.grep，路径受逻辑沙箱限制。
---

# 工作区文件（只读沙箱）

当用户说「读一下某文件」「搜一下工作区」「打开 AGENTS.md」等：

1. 路径已知 → 调用 `fs.read`，`path` 用相对 workspace 的路径
2. 路径未知 → 先 `fs.grep`（`query` + 可选 `path`/`glob`），再按需 `fs.read`
3. 只根据工具返回内容回答；不要编造文件内容
4. 若工具返回 `policy_denied` / path escape，说明被沙箱拦住，不要尝试绝对路径逃逸
5. 当前阶段没有 `fs.write` / `exec`，不要声称已修改文件或执行命令
