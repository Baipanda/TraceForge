# Todo Show 项目工作总结报告

## 一、项目概述

基于已有 PostgreSQL 中的 Todo 数据，构建了一套完整的 Todo 管理 Web 应用。支持列表浏览、详情查看、新建编辑、分类树、操作日志等功能。

**技术栈：** FastAPI + psycopg2（后端）/ Vue 3 + Vite + Bootstrap 5（前端）/ Docker Compose（部署）

**用户使用说明：** [USER_GUIDE.md](USER_GUIDE.md)

---

## 二、数据库分析

| 表 | 行数 | 用途 |
|----|------|------|
| `people` | 27 | 人员信息 |
| `person_aliases` | 47 | 人员别名 |
| `projects` | 3 | 项目（2503、专利、学习） |
| `subtrees` | 23 | 分类树（自引用层级结构） |
| `todos` | 动态 | 核心 Todo 表（含 Bug 标记、父子关系、工作占比和多种角色数组） |
| `todo_progress_history` | 动态 | Todo 同步进展历史（内容、填写人、填写时间） |

---

## 三、后端 API（16 个端点）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/health` | 健康检查（含数据库连通性） |
| GET | `/api/stats` | 统计数据（工作状态、Bug、优先级、同步安排） |
| GET | `/api/people` | 人员列表 |
| GET | `/api/projects` | 项目列表 |
| GET | `/api/subtrees` | 分类树（嵌套 JSON） |
| GET | `/api/todos` | 分页列表（支持 Bug、工作状态、同步安排、人员、父 Todo 等筛选） |
| GET | `/api/todos/{id}` | 单条详情（含子 Todo/依赖/人员姓名） |
| PUT | `/api/todos/{id}/child-weights` | 批量修改直接子 Todo 的整数占比，并重新汇总父项状态 |
| POST | `/api/todos` | 新建 Todo |
| PUT | `/api/todos/{id}` | 更新 Todo |
| DELETE | `/api/todos/{id}` | 软删除 |
| GET/POST | `/api/todos/{id}/progress` | 查询或填写 Todo 同步进展 |
| GET | `/api/subtrees/{id}/todos` | 按分类查看 Todo |
| GET | `/api/logs` | 操作日志查询 |
| POST/PUT/DELETE | — | 自动记录操作日志 |

---

## 四、前端页面

| 路由 | 视图 | 功能 |
|------|------|------|
| `/` | TodoList.vue | 默认树形列表：Bug 标记和筛选、可配置列、同步安排、组合筛选、填写进展、一键完成 |
| `/todos/:id` | TodoDetail.vue | 详情页：查看/编辑 Bug 类型、父子关系、子项占比、依赖链、角色人员、同步状态及进展时间线 |
| `/create` | TodoCreate.vue | 新建页：完整表单（含搜索过滤的下拉选择） |
| `/tree` | TreeView.vue | 分类树：递归展开折叠、点击跳转筛选 |
| `/logs` | LogsView.vue | 操作日志：按操作类型/用户筛选、分页、目标可跳转详情 |

**共享组件：** TodoForm.vue（新建/编辑复用，含搜索过滤）、TreeNode.vue（递归树节点）、NotFound.vue（404）

---

## 五、已修复的问题

### 严重问题

| # | 问题 | 修复 |
|---|------|------|
| 1 | 数据库密码硬编码在源代码中 | 移除默认值，改为必填环境变量 `DATABASE_URL` |
| 2 | SQL 异常不 rollback 导致连接池污染 | `query()`/`execute()` 添加 `try/except + conn.rollback()` |
| 3 | `depends_on_ids` UUID 类型不匹配导致 500 | 注册 `psycopg2.extras.register_uuid()` + 显式转换 |
| 4 | `proposer_id` NOT NULL 约束导致新建失败 | 后端默认 1，前端默认选中第一人 |
| 5 | `update_todo` 不校验 status/priority | 增加白名单校验，非法值返回 400 |
| 6 | `subtree_id` 无存在性校验 | 创建前查询，不存在返回 400 |

### 功能问题

| # | 问题 | 修复 |
|---|------|------|
| 7 | 列表页缺少"父 Todo"列 | API 返回 `parent_title`，列表页新增该列 |
| 8 | 详情页缺少"父 Todo"和"Todo ID" | 右侧信息卡增加两行，父 Todo 可点击跳转 |
| 9 | 同组件路由切换不刷新 | 添加 `watch` + `router-view :key` |
| 10 | 父 Todo 下拉选择 200 条难找 | 单选用搜索下拉，多选用搜索输入框过滤 |
| 11 | 表单缺少角色字段 | 补充 depends_on_ids + 5 种人员多选 |
| 12 | 软删除父 Todo 显示断链 | SQL join 排除已删除，前端显示"(已删除)" |
| 13 | `_names()` 返回顺序错乱 | 改用 lookup dict 保持输入顺序 |
| 14 | `completed_at` 回退不清零 | 状态非 completed 时自动 SET NULL |
| 15 | 前端加载失败无提示 | 添加 error 状态 + 重试按钮 |
| 16 | 无 404 页面 | 新增 NotFound.vue + catch-all 路由 |
| 17 | Health 端点不查数据库 | 增加 `SELECT 1` 检查 |

### 操作日志系统

| # | 功能 |
|---|------|
| 18 | 创建 `operation_logs` 表（username/action/target/detail/timestamp） |
| 19 | 后端所有写操作自动记录日志 |
| 20 | 用户身份选择系统（全屏遮罩，必须选择才能进入） |
| 21 | 操作日志查看页面（筛选/分页/跳转） |
| 22 | X-User 请求头自动注入（window 全局变量 + 请求级 config） |

### 同步进展系统

| # | 功能 |
|---|------|
| 23 | Todo 可配置同步频率和可编辑的进展填写提示 |
| 24 | 每次填写进展写入 `todo_progress_history`，并记录填写人与操作日志 |
| 25 | 同步状态按上海自然日计算：今日已同步、今日待同步、已逾期、计划中、未设置、已结束 |
| 26 | 同步安排与同步状态分离，支持当前需同步、今日已同步、已逾期、今日到期、未来 3/7 天筛选 |
| 27 | 填写进展后显示“今日已填写”，并提供独立确认按钮 |
| 28 | 同步流程拆分为“填写进展”和“确认同步”，仅确认后推进下一次同步时间 |
| 29 | 列表默认显示主力人员或流程管理人员包含当前用户的 Todo，并支持关闭“只看与我相关” |
| 30 | 列表支持树形视图，自动补齐父级路径并逐层展开子 Todo |
| 31 | 未确认进展超过原同步日期时显示红色“待确认（已逾期）” |
| 32 | Todo 支持高、普通、低三级优先级，并支持筛选与排序 |
| 33 | 列表采用稳定排序，填写、确认或完成 Todo 后保持当前相对顺序 |
| 34 | 从详情返回树形列表时恢复展开层级、滚动位置并高亮原 Todo |
| 35 | 父 Todo 的直接子项均结束时自动完成；已完成、已取消、已过期均视为结束，并支持多级递归汇总 |
| 36 | 所有处理中子 Todo 今日均已确认后，父 Todo 自动生成同步汇总；条件变化时自动失效并保留审计记录 |
| 37 | 系统界面隐藏提出人和跟踪人，数据库字段及后端兼容能力继续保留 |
| 38 | 优先级恢复为高、普通、低三级，历史紧急事项自动调整为高 |
| 39 | 首页同步状态旁增加历史按钮，弹窗展示最近 3 条同步记录 |
| 40 | 子 Todo 支持整数工作占比；父项仅在子项全部结束且占比合计 100% 时自动完成 |
| 41 | 父 Todo 详情页支持批量调整直属子项占比，并显示父项自身剩余占比 |
| 42 | Todo 新增 `is_bug` 类型标记，历史数据默认 `false`，创建和编辑均可修改 |
| 43 | 列表支持 Bug 筛选和紧凑标识，详情页、统计和操作日志同步展示或记录 Bug 属性 |

---

## 六、项目结构

```
todo_show/
├── .env
├── .gitignore
├── docker-compose.yml
├── summary.md                     # 本报告
├── USER_GUIDE.md                  # 用户使用指南
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── database.py                # 连接池 + UUID 注册 + rollback
│   ├── schemas.py                 # Pydantic 模型
│   └── main.py                    # FastAPI 全部路由
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        ├── App.vue
        ├── api/index.js
        ├── views/
        │   ├── TodoList.vue
        │   ├── TodoDetail.vue
        │   ├── TodoCreate.vue
        │   ├── TreeView.vue
        │   ├── LogsView.vue
        │   └── NotFound.vue
        └── components/
            ├── TodoForm.vue
            └── TreeNode.vue
```

---

## 七、启动方式

**Docker：**
```bash
docker-compose up -d
# http://localhost
```

**本地开发：**
```bash
# 后端
cd backend
DATABASE_URL="postgresql://..." uvicorn main:app --port 8000

# 前端
cd frontend
npm run dev
# http://localhost:3000
```

---

## 八、已知待改进项

1. 依赖项可视化管理较薄弱（当前以列表展示为主）
2. 暂无自动化端到端测试，关键页面交互仍需在发布前人工验收
