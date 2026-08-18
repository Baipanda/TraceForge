# TraceForge 独立 Zulip

这套 compose 只用于 TraceForge 开发和演示，不能连接或修改当前机器上正在使用的既有 Zulip / OpenClaw。

## 隔离资源

- 容器名：`traceforge-zulip-*`
- HTTP：`18080`
- HTTPS：`18443`
- PostgreSQL：`15433`
- 数据卷：`traceforge-zulip-*`

## 启动前检查

```bash
docker ps --format '{{.Names}} {{.Ports}}' | grep -E 'traceforge|18080|18443|15433'
```

确认没有输出后再启动。

## 启动

```bash
cd workspace/traceforge/deploy/zulip
cp .env.example .env
docker compose --project-name traceforge-zulip up -d
```

换服务器时必须先修改 `.env` 中的：

```text
TRACEFORGE_ZULIP_EXTERNAL_HOST=<服务器IP或域名>:18443
TRACEFORGE_ZULIP_FAKE_EMAIL_DOMAIN=traceforge.local
```

如果使用 IP 地址访问 Zulip，`TRACEFORGE_ZULIP_FAKE_EMAIL_DOMAIN` 仍然必须是合法域名格式，不能写成 IP。

浏览器访问：

```text
https://192.168.52.225:18443
```

首次会使用自签名证书，需要浏览器手动信任。

## 重要限制

- 不要使用 `/home/baijy/workspace/docker-zulip` 的配置。
- 不要使用现有 Zulip Bot。
- 不要把 TraceForge Bot 加到现有 Zulip。
- 不要复用现有 Zulip 数据库或数据卷。
