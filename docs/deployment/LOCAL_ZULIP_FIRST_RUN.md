# 独立 Zulip + TraceForge 首次跑通方案

目标不是一次性做完整产品，而是先跑通最小闭环：

```text
Zulip / smoke payload
  -> TraceForge HTTP endpoint
  -> Zulip Adapter normalizer
  -> WorkspaceEvent
  -> Application Use Case
  -> JSON reply
```

## 0. 强约束：不影响现有服务

当前机器上正在运行的 Zulip / OpenClaw 是生产式使用中的现有部署。TraceForge 的部署、调试和实验必须完全避开它们。

禁止操作：

- 不停止现有 Zulip / OpenClaw 容器
- 不重启现有 Zulip / OpenClaw 服务
- 不修改现有 Zulip / OpenClaw 配置
- 不连接现有 Zulip Bot 凭证
- 不写入现有 `openclaw_todo` 数据库
- 不复用现有容器名、端口和数据卷

TraceForge 使用独立端口、独立容器名、独立数据库、独立 Zulip Bot。

## 1. Zulip 部署边界

TraceForge 的 GitHub 项目不内置 Zulip 源码，也不修改 Zulip 数据库。

推荐部署方式只有一种：

- 单独部署一套 TraceForge 专用 Zulip Docker，再把 TraceForge 作为独立服务接入。

TraceForge 只通过 adapter 使用 Zulip：

- Zulip API
- Zulip event queue
- Zulip Bot 凭证

建议独立端口：

```text
TraceForge Zulip HTTPS: 18443
TraceForge Zulip HTTP: 18080
TraceForge Zulip Postgres: 15433
TraceForge API: 19090
TraceForge Postgres: 15432
TraceForge Redis: 16380
```

## 2. 启动 TraceForge

```bash
cd workspace/traceforge
cp .env.example .env
python -m uvicorn traceforge.server:app --host 0.0.0.0 --port 19090
```

健康检查：

```bash
curl http://127.0.0.1:19090/health
```

如果用 Docker Compose：

```bash
cd workspace/traceforge/deploy
docker compose --project-name traceforge-stack up -d
curl http://127.0.0.1:19090/health
```

## 3. 不接 Zulip 时先做 smoke test

```bash
cd workspace/traceforge
PYTHONPATH=src python scripts/smoke_zulip_event.py
```

这会模拟一条 Zulip 消息：

```text
@TraceForge 给李四发布一个 todo：检查认证模块 SQL 注入风险
```

## 4. 下一步接真实 Zulip

第一阶段接入方式：

```text
traceforge.interfaces.zulip.poller
  -> 调用独立 Zulip Bot API 长轮询
  -> 收到 @bot 消息
  -> POST /api/events/zulip
```

第二阶段再把 poller 合并进 TraceForge worker。

## 5. 为什么先这样做

这个方案借鉴了现有 Zulip bridge 的事件接入思路，但不复用它的运行时，也不引入任何 OpenClaw 命名。

我们先证明 TraceForge 自己能跑：

- 有 HTTP 服务
- 有 Zulip adapter
- 有 WorkspaceEvent
- 有 Application Use Case

然后再接 Todo、RAG、Agent Runtime。先让心跳响起来，再给它装肌肉。
