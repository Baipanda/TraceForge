docs_root: `workspace_shared/docs/todo-show`

### PRD.md
# Todo Show — 产品需求（演示用）

## 目标

为研发团队提供可检索的 Todo 工作空间：任务、人员、分类树、进展与操作日志。

## 范围

- 树形 Todo（父子、依赖、工作占比）
- 多角色人员（主力 / 备份 / 顾问等）
- 分类 subtree 与项目归属
- 进展填写与同步确认

## 非目标

- 不替代 IDE / 代码托管
- 不自动写业务代码

## 验收点（演示）

1. 能按 subtree 列出未完成 Todo
2. 能从 Zulip Topic 回链到任务
3. 进度体检（progress-sop）能读到本 PRD 并对照任务缺口

### TECH.md
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

### STATUS.md
# Todo Show — 当前状态（演示）

- 参考实现位于 `references/todo-show`
- 用于 TraceForge **progress-sop** 端到端演示样例
- 已知关注点：父子占比滚动、Bug 标记、操作日志完整性