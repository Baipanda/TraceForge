# TraceForge 独立部署隔离规则

TraceForge 的开发部署必须和当前机器上的现有 Zulip / OpenClaw 完全隔离。

## 命名规则

容器名必须使用 `traceforge-` 前缀：

- `traceforge-app`
- `traceforge-postgres`
- `traceforge-redis`
- `traceforge-zulip-*`
- `traceforge-gitea`

数据卷必须使用 `traceforge-` 前缀：

- `traceforge-postgres-data`
- `traceforge-zulip-postgres-data`
- `traceforge-zulip-data`
- `traceforge-gitea-data`

数据库名使用：

- `traceforge`
- `traceforge_todo`

不要使用任何旧系统命名。

## 端口规则

不要占用现有服务端口。

推荐端口：

| 服务 | 端口 |
|---|---:|
| TraceForge API | `19090` |
| TraceForge PostgreSQL | `15432` |
| TraceForge Redis | `16380` |
| TraceForge Zulip HTTPS | `18443` |
| TraceForge Zulip HTTP | `18080` |
| TraceForge Zulip PostgreSQL | `15433` |
| TraceForge Gitea HTTP | `13000` |
| TraceForge Gitea SSH | `12222` |

## 数据规则

- TraceForge 不写现有 Zulip 数据库。
- TraceForge 不写现有 Todo 数据库。
- TraceForge 不读取现有 Helper 配置作为运行依赖。
- Demo 数据由 seed 脚本生成。
- 如需参考现有数据，只做匿名样例，不复制全量。

## 操作规则

除非用户明确要求，否则不得执行：

- `docker stop` 现有服务
- `docker restart` 现有服务
- 修改 `/home/baijy/workspace/docker-zulip`
- 修改 `/home/baijy/.openclaw`
- 修改现有 Zulip Bot

TraceForge 的实验只在 `workspace/traceforge` 和 `traceforge-*` 资源中进行。
