## RepoAudit 进度审查：`todo-show`
- 时间：2026-09-04 11:01 UTC
- 仓库：traceforge/TraceForge@main
- 模式：**只审不写**（不生成业务代码、不开 PR）

### 对齐判断
- 有文档与任务信号，可做对齐检查

### 文档侧
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

### 讨论侧（main 摘要）
#sandbox / todo-show开发 · 共 5 条，展示最近 5 条：
- [09-04 10:45] Admin: 讨论：父子占比滚动还有边界 case 要补测试。
- [09-04 10:45] Admin: 阻塞：Bug 标记筛选和列表页还没对齐 USER_GUIDE。
- [09-04 10:45] Admin: @Jarvis 项目进度：todo-show
- [09-04 11:01] Admin: @**Jarvis** 项目进度：todo-show
- [09-04 11:01] Admin: @**Jarvis** sop continue run_id=d27b2fb0-5a4b-47ab-9581-9c294dd21fec window=7 include_audit=1 focus=blocked

### 任务侧（main 摘要）
Todo Summary
- 总数：0
- 暂无条目

### 风险与缺口
- 未发现明显结构性缺口

### 建议（由人写代码）
1. 对照 PRD 验收点核对未完成 Todo
2. 把讨论里的未决问题收敛成可执行任务
3. 代码变更仍由开发者提交；RepoAudit 仅跟审查结论
