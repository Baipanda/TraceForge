# Todo Show — 技术方案（演示用）

## 架构

- 前端：Vue 3 + Vite
- 后端：FastAPI + PostgreSQL
- 与 TraceForge：Jarvis 经 HTTP API 创建/查询/更新 Todo

## 约束

- 后端不使用 ORM；连接与事务在 `database.py`
- TraceForge Agent **不直接写 Todo Show SQL**
- RepoAudit / gitea-audit **只审查不对齐与风险，不写代码**

## 与 progress-sop 的关系

- Project Admin 绑定：`docs_root`、`subtree_code`、Zulip Topic、可选 Gitea
- Audit 步消费本文档 + Topic/Todo 摘要
