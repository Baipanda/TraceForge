# 新服务器从零部署 TraceForge

这份文档回答一个核心问题：如果不在当前机器上复用任何已有环境，TraceForge 应该如何在一台新服务器上独立跑起来。

## 1. 部署边界

TraceForge 项目不依赖当前机器上的 Zulip / OpenClaw / todo-show。

在新服务器上，需要部署两组独立服务：

- TraceForge 应用栈：TraceForge API、TraceForge PostgreSQL、TraceForge Redis
- TraceForge 专用 Zulip 栈：Zulip Server、Zulip PostgreSQL、Memcached、RabbitMQ、Redis

Zulip 是 TraceForge 的协作入口和消息 UI，不是 TraceForge 的核心运行时。TraceForge 通过 Zulip Bot/API 接入 Zulip。

## 2. 镜像来源

TraceForge 自己的应用镜像由本仓库 `Dockerfile` 构建。

| 服务 | 镜像 | 来源 |
|---|---|---|
| TraceForge API base | `docker.io/library/python:3.12-slim` | Docker Hub official image |
| TraceForge PostgreSQL | `docker.io/library/postgres:16-alpine` | Docker Hub official image |
| TraceForge Redis | `docker.io/library/redis:7-alpine` | Docker Hub official image |
| Zulip Server | `ghcr.io/zulip/zulip-server:12.0-1` | GitHub Container Registry |
| Zulip PostgreSQL | `docker.io/zulip/zulip-postgresql:14` | Docker Hub Zulip image |
| Zulip Memcached | `docker.io/library/memcached:alpine` | Docker Hub official image |
| Zulip RabbitMQ | `docker.io/library/rabbitmq:4.2` | Docker Hub official image |
| Zulip Redis | `docker.io/library/redis:alpine` | Docker Hub official image |

这些镜像已经写在：

- `Dockerfile`
- `deploy/docker-compose.yml`
- `deploy/zulip/docker-compose.yml`

换服务器时，`docker compose up -d` 会自动从 Docker Hub / GitHub Container Registry 拉取这些镜像。

## 3. 新服务器前置条件

服务器需要：

- Linux
- Docker Engine
- Docker Compose v2
- 能访问 `docker.io`
- 能访问 `ghcr.io`
- 开放需要的端口

默认端口：

| 用途 | 默认端口 |
|---|---|
| TraceForge API | `19090` |
| TraceForge PostgreSQL | `15432` |
| TraceForge Redis | `16380` |
| TraceForge Zulip HTTP | `18080` |
| TraceForge Zulip HTTPS | `18443` |
| TraceForge Zulip PostgreSQL | `15433` |

如果服务器已有服务占用这些端口，需要在 `.env` 中改端口。

## 4. 部署 TraceForge 应用栈

```bash
cd workspace/traceforge
cp .env.example .env
cd deploy
docker compose --project-name traceforge-stack up -d
```

验证：

```bash
curl http://127.0.0.1:19090/health
```

预期返回：

```json
{"ok":true,"service":"traceforge","status":"healthy"}
```

## 5. 部署 TraceForge 专用 Zulip

```bash
cd workspace/traceforge/deploy/zulip
cp .env.example .env
```

必须按新服务器修改：

```text
TRACEFORGE_ZULIP_EXTERNAL_HOST=<服务器IP或域名>:18443
TRACEFORGE_ZULIP_FAKE_EMAIL_DOMAIN=traceforge.local
TRACEFORGE_ZULIP_ADMIN=traceforge-admin@example.local
```

如果使用 IP 地址作为 `TRACEFORGE_ZULIP_EXTERNAL_HOST`，必须保留一个合法域名格式的 `TRACEFORGE_ZULIP_FAKE_EMAIL_DOMAIN`，例如 `traceforge.local`。否则 Zulip 注册用户时会把 IP 当作 email domain，导致注册失败。

启动：

```bash
docker compose --project-name traceforge-zulip up -d
```

验证：

```bash
curl -k -I https://<服务器IP或域名>:18443/login/
```

## 6. 首次创建 Zulip 组织

进入 Zulip 容器生成一次性组织注册链接：

```bash
docker exec -u zulip traceforge-zulip \
  /home/zulip/deployments/current/manage.py generate_realm_creation_link
```

用生成的链接创建 TraceForge 专用组织。

如果组织创建成功但用户注册失败，通常是 `TRACEFORGE_ZULIP_FAKE_EMAIL_DOMAIN` 没配好。修正 `.env` 后，只重建独立 Zulip 容器：

```bash
docker compose --project-name traceforge-zulip up -d --force-recreate traceforge-zulip
```

## 7. 为什么不把 Zulip 打进 TraceForge 镜像

TraceForge 和 Zulip 应该保持解耦：

- Zulip 是成熟协作系统，负责用户、Channel、Topic、消息存储和 Bot API。
- TraceForge 是 Agent 系统，负责事件理解、上下文构建、工具调用、任务闭环和审计。
- 用 Docker Compose 编排两者，比把 Zulip 嵌进 TraceForge 镜像更清晰，也更接近真实工程部署。

这个设计借鉴了优秀系统中的 adapter / integration 思路：外部系统作为可替换入口接入，核心 Agent Runtime 不绑定具体 UI。
