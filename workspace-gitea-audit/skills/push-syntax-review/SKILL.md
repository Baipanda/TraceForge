---
name: push-syntax-review
description: 在 Gitea push 后检查变更文件的 Python/JSON 语法，并给出修正建议。
---

# Push 语法检查

当收到 push 事件时：

1. 从 payload 收集 added/modified 路径
2. 拉取 `after` 版本文件内容
3. 对 `.py` 用 AST、对 `.json` 用 json.loads 校验
4. 把问题与建议附在 Zulip 通知后

不要声称已修改仓库。
