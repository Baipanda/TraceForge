# Todo Show

面向研发团队的 Todo 管理系统：把任务、人员、分类、进展同步和操作记录放到同一套可检索的工作空间里。

TraceForge 将它作为任务域扩展接入。Jarvis 在 Zulip 中创建、查询和更新 Todo 时，走本系统的 HTTP API，而不是在 Agent 内再实现一套任务库。

使用说明见 [USER_GUIDE.md](USER_GUIDE.md)。功能清单与接口一览见 [SUMMARY.md](SUMMARY.md)。

## 能力

- 树形任务列表，支持父子 Todo、依赖和整数工作占比
- 人员多角色：主力、备份、流程管理、技术顾问、关注者
- 分类树（subtree）与项目归属
- 进展填写与同步确认分离，按频率计算逾期和到期状态
- Bug 标记、优先级、软删除
- 操作日志（创建 / 更新 / 删除 / 进展 / 确认）
- 可选记录 Zulip stream、topic 和来源消息 ID，便于从讨论回链到任务

## 架构

```text
Browser (Vue 3 + Vite)
        |
        v
     nginx / Vite proxy
        |
        v
 FastAPI  (/api/*)
        |
        v
    PostgreSQL
```

- 后端：FastAPI、psycopg2、Pydantic
- 前端：Vue 3、Vue Router、Bootstrap 5
- 部署：Docker Compose，前后端分容器

后端不使用 ORM。连接池、事务和查询封装在 `backend/database.py`，路由与业务规则在 `backend/main.py`，请求/响应契约在 `backend/schemas.py`。

## 目录

```text
todo-show/
├── backend/                 # FastAPI 服务
│   ├── main.py
│   ├── database.py
│   ├── schemas.py
│   └── tests/
├── frontend/                # Vue 3 应用
│   └── src/
│       ├── api/index.js     # HTTP 客户端（X-User 身份头）
│       ├── views/
│       └── components/
├── migrations/              # SQL 迁移
├── docker-compose.yml
├── USER_GUIDE.md
└── SUMMARY.md
```

## HTTP API

认证方式：请求头 `X-User` 传入操作者姓名，用于写操作审计。当前不是完整的账号权限系统。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（含数据库连通性） |
| GET | `/api/stats` | 工作状态、优先级、同步安排统计 |
| GET | `/api/people` | 人员列表 |
| GET | `/api/projects` | 项目列表 |
| GET | `/api/subtrees` | 分类树 |
| GET | `/api/todos` | 分页列表，支持状态、人员、父项、Topic 相关筛选 |
| GET | `/api/todos/{id}` | 详情，含子项、依赖、角色和进展摘要 |
| POST | `/api/todos` | 创建 |
| PUT | `/api/todos/{id}` | 更新 |
| PUT | `/api/todos/{id}/child-weights` | 批量设置直属子项占比并汇总父项 |
| DELETE | `/api/todos/{id}` | 软删除 |
| GET/POST | `/api/todos/{id}/progress` | 查询或填写进展 |
| POST | `/api/todos/{id}/progress/{progress_id}/confirm` | 确认同步 |
| GET | `/api/logs` | 操作日志 |
| GET | `/api/subtrees/{id}/todos` | 按分类列出 Todo |

创建 Todo 时与工作空间相关的字段：

- `title`、`description`、`priority`、`is_bug`
- `subtree_id`、`project_id`、`parent_id`、`depends_on_ids`
- `main_force_ids` 等角色数组
- `zulip_stream`、`zulip_topic`、`source_message_id`
- `track_frequency`、`progress_prompt`

## 作为 TraceForge 扩展

推荐边界：

```text
Zulip @Jarvis
  -> TraceForge Gateway / Agent Runtime
  -> Tool (todo.create / todo.list / todo.get / todo.update)
  -> Todo Show HTTP API
  -> PostgreSQL
```

接入时注意：

1. TraceForge 只依赖本 README 中的 API 契约，不直接读写 Todo Show 数据库。
2. 从 Zulip 创建任务时写入 `zulip_stream`、`zulip_topic`，保证「这个问题修了吗」可以按 Topic 回查。
3. 人员解析应对齐 `people` / 别名，而不是把 Zulip 显示名直接当负责人主键。
4. 写操作带上 `X-User`，让 Todo Show 侧的 `operation_logs` 成为审计来源之一。
5. 幂等和字段校验以 Todo Show 的业务规则为准（负责人存在、状态白名单、软删除、父项汇总）。
6. TraceForge 的 MVP 可以只使用创建、查询、按 Topic 过滤和状态更新；父子占比、同步频率等能力按需打开。

## 运行

复制环境变量并填写数据库连接：

```bash
cp .env.example .env
```

Docker Compose：

```bash
docker compose up -d --build
```

默认前端 `3080`，后端 `8010`，可在 `.env` 中修改 `FRONTEND_PORT` / `BACKEND_PORT`。

本地开发：

```bash
# 后端
cd backend
DATABASE_URL="postgresql://todo:todo@127.0.0.1:5432/todo_show" \
  uvicorn main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev
```

数据库 schema 由 `migrations/` 下的 SQL 按文件名顺序演进，使用 `backend/apply_migrations.py` 应用。

## 测试

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
