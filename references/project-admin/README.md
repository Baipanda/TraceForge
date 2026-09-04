# Project Admin（Project Ledger）

Mentor 后台：维护 TraceForge **项目名片**（Zulip Topic、共享文档路径、Gitea 仓库、成员、Todo subtree 等）。  
**不修改** `references/todo-show`。Agent / 进度 SOP 只通过只读 API 查询，不在 Zulip 里改项目绑定。

## 能力

- 项目增删改查（删除=归档）
- 成员增删（owner / pm / dev / reviewer / mentor）
- SOP 报告入库与 Markdown 展示（供后续 progress-sop 回写）
- 只读解析：`GET /api/projects/resolve?project_id=` 或 `stream`+`topic`

## 架构

```text
Browser (Vue 3 + Vite)
   → /api proxy
FastAPI
   → SQLite  data/project_admin.sqlite3
```

## 快速启动

### 1. 后端

```bash
cd references/project-admin/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python apply_migrations.py
uvicorn main:app --reload --host 127.0.0.1 --port 18081
```

> 说明：本机 `18080` 可能已被其它服务占用，默认改用 **18081**。
写操作需请求头：`X-Mentor: traceforge-admin`（默认名单仅此一人，可用环境变量 `PROJECT_ADMIN_MENTORS` 覆盖）。

### 2. 前端

```bash
cd references/project-admin/frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5177 ，选择 Mentor 后进入。

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/mentors` | Mentor 名单 |
| GET/POST | `/api/projects` | 列表 / 创建 |
| GET/PUT/DELETE | `/api/projects/{id}` | 详情 / 更新 / 归档 |
| GET | `/api/projects/resolve` | Agent 用：按 id 或 stream+topic |
| POST/DELETE | `/api/projects/{id}/members` | 成员 |
| GET | `/api/projects/{id}/reports` | 项目 SOP 报告列表 |
| GET/POST | `/api/reports`、`/api/reports/{id}` | 报告读写 |

## 与 TraceForge / todo-show

| 系统 | 职责 |
|------|------|
| **project-admin** | 项目主数据与 SOP 报告展示 |
| **todo-show** | 任务 CRUD（可选 `todo_show_project_id` 对齐） |
| **TraceForge Agent** | 只读 `resolve` / `get`，驱动进度 SOP |

数据库默认：`references/project-admin/data/project_admin.sqlite3`  
可用 `PROJECT_ADMIN_DB` 覆盖路径。
