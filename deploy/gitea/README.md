# TraceForge 独立 Gitea

轻量 Git 托管，仅用于 TraceForge 开发/演示，与现有 Zulip / OpenClaw 隔离。

**不走网页安装向导**（Docker 下易失败），启动时自动 migrate 并创建管理员。

## 资源

| 项 | 值 |
|---|---|
| 容器 | `traceforge-gitea` |
| HTTP | http://127.0.0.1:13000 |
| SSH | `12222` |
| 数据卷 | `traceforge-gitea-data` |
| 数据库 | 容器内 SQLite |

## 启动

```bash
cd deploy/gitea
cp .env.example .env   # 若还没有 .env
docker compose --project-name traceforge-gitea up -d
```

浏览器打开：

```text
http://127.0.0.1:13000
```

默认管理员（见 `.env`，可改）：

```text
用户名: gitea-admin
密码:   TraceForge@2026
邮箱:   gitea-admin@traceforge.local
```

登录后即可建仓库、加用户。

## Webhook → TraceForge → RepoAudit

组织 **TraceForge** 已可配置（或已配置）org webhook：

```text
URL:    http://traceforge-app:8090/api/events/gitea
Secret: 与 TRACEFORGE_GITEA_WEBHOOK_SECRET 一致（默认见仓库 .env）
Events: push / pull_request / issues / …
```

Gitea 容器需与 `traceforge-app` 同网（compose 已挂 `deploy_default`）。  
出站通知发到 Zulip `general` / topic `gitea`，署名 **RepoAudit**。

本地冒烟：

```bash
# 向 demo 仓 push 后，看 Zulip general → gitea
# 或直接 POST（注意签名要按原始 body 计算）
curl -s http://127.0.0.1:19090/health
```

## 停止 / 重置

```bash
cd deploy/gitea
docker compose --project-name traceforge-gitea down      # 保留数据
docker compose --project-name traceforge-gitea down -v   # 清空数据并重装
```

## 隔离说明

- 不占用 `18443` / `19090` / `15432` 等现有端口
- 不连接现有 OpenClaw / 生产 Zulip
- Webhook 经 TraceForge `/api/events/gitea`，再由 RepoAudit 发 Zulip（不直连）
