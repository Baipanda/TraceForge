# References

本目录存放 TraceForge 计划作为扩展接入的独立系统。每个子目录都是一套可单独运行的产品，拥有自己的数据模型、HTTP API 和用户界面。

TraceForge 通过稳定的外部接口与这些系统协作，而不是把对方的运行时、数据库或前端并入 Agent 内核。

## 模块

| 模块 | 定位 | 接入面 |
|---|---|---|
| [todo-show](todo-show/README.md) | 团队 Todo 管理：任务生命周期、人员角色、进展同步与操作审计 | REST API（`/api/todos` 等） |
| [project-admin](project-admin/README.md) | Mentor 项目名片：Topic/文档/Gitea/成员绑定与 SOP 报告展示 | REST API（`/api/projects`、`/api/reports`） |

## 接入原则

- 扩展系统保持独立部署，使用自己的数据库和配置。
- TraceForge 只依赖文档化的 HTTP 契约和领域字段（例如 Todo 的 Topic 来源）。
- Agent 通过 Tool 调用扩展能力，不直接访问扩展系统的数据库。
- 写入类操作必须可审计、可幂等；扩展侧已有的日志与状态机应被复用，而不是在 Agent 内再实现一份。
