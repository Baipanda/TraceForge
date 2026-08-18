# TraceForge 当前部署状态

更新时间：2026-08-17

## 隔离原则

本次部署只创建和启动 `traceforge-*` 资源，没有停止、重启或修改当前机器上已有的 Zulip / OpenClaw 服务。

## 已启动服务

| 服务 | 容器名 | 端口 |
|---|---|---|
| TraceForge API | `traceforge-app` | `19090 -> 8090` |
| TraceForge PostgreSQL | `traceforge-postgres` | `15432 -> 5432` |
| TraceForge Redis | `traceforge-redis` | `16380 -> 6379` |
| TraceForge Zulip | `traceforge-zulip` | `18080 -> 80`, `18443 -> 443` |
| TraceForge Zulip PostgreSQL | `traceforge-zulip-database` | `15433 -> 5432` |
| TraceForge Zulip Memcached | `traceforge-zulip-memcached` | internal |
| TraceForge Zulip RabbitMQ | `traceforge-zulip-rabbitmq` | internal |
| TraceForge Zulip Redis | `traceforge-zulip-redis` | internal |

Zulip bridge 当前不作为 Docker 容器运行。当前推荐方式是在项目目录中以本机进程启动：

```bash
python scripts/run_zulip_bridge.py
```

## 验证结果

TraceForge API：

```bash
curl http://127.0.0.1:19090/health
```

返回：

```json
{"ok":true,"service":"traceforge","status":"healthy"}
```

模拟 Zulip 事件：

```bash
PYTHONPATH=src python scripts/smoke_zulip_event.py
```

结果：TraceForge 能把模拟 Zulip payload 标准化为 `WorkspaceEvent`，并识别出 `todo.command` 意图。

真实 Zulip bridge：

```text
Zulip @Jarvis -> TraceForge API -> DeepSeek -> Jarvis 回帖
```

结果：已验证公共 Topic 中 `@Jarvis` 可以触发 bridge，并由 Jarvis 回帖到同一 Topic。

独立 Zulip：

```bash
curl -k -I https://192.168.52.225:18443
```

结果：容器 healthy，HTTPS 登录页有响应。

## 独立 Zulip 组织

组织名：`TraceForge`

访问地址：

```text
https://192.168.52.225:18443/login/
```

开发管理员账号：

```text
email: traceforge-admin@example.local
password: TraceForge@2026
```

说明：由于本机演示环境使用 `192.168.52.225:18443` 这种 IP 地址作为 Zulip `EXTERNAL_HOST`，需要配置 `SETTING_FAKE_EMAIL_DOMAIN=traceforge.local`。否则 Zulip 在注册用户时会尝试把 IP 当作 email domain，触发 `InvalidFakeEmailDomainError`。

## 常用命令

查看 TraceForge 资源：

```bash
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}' | sort | grep '^traceforge'
```

停止 TraceForge API / DB / Redis：

```bash
cd workspace/traceforge/deploy
docker compose --project-name traceforge-stack down
```

停止 TraceForge 独立 Zulip：

```bash
cd workspace/traceforge/deploy/zulip
docker compose --project-name traceforge-zulip down
```

注意：这些命令只影响 `traceforge-*` 资源。
