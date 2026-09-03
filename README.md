# TraceForge

TraceForge 是一个面向研发/安全团队的 Workspace Agent 产品。

它把 Zulip 讨论、任务、文档、代码仓库和安全事件转化为可追踪、可执行、可审计的智能体工作流。

## 代码与 Agent Workspace

```text
src/traceforge/          # 工程源码
workspace/               # Agent 工作区
  AGENTS.md
  IDENTITY.md
  TOOLS.md
  MEMORY.md
  skills/
  scripts/
```

`src/traceforge` 负责稳定的系统实现；`workspace` 负责 Agent 身份、行为约定、Skills 和可调整的业务流程。

当前已经加入 Markdown 记忆子系统：工作区文件为权威源，SQLite FTS/embedding 为派生索引；会话 transcript 走 JSONL。

当前运行边界：

```text
Zulip Adapter -> HTTP API -> Context Builder -> Session Resolver -> Gateway -> 当前事件处理器
```

后续 Agent 化边界：

```text
interfaces/      # Zulip、HTTP 等外部入口适配
gateway/         # 统一入口、会话、权限、路由、审计入口
agent/           # Runtime、Harness、SkillLoader、运行轨迹模型
tools/           # ToolRegistry、本地工具与未来 MCP 工具适配
application/     # 确定性业务用例，例如 Todo 写入、权限校验、事务编排
core/            # 核心业务对象和规则
infrastructure/  # LLM、数据库、Zulip API、外部服务实现
```

其中 `runtime` 和 `harness` 不再作为顶层包存在，而是归入 `agent/`。`ToolRegistry` 独立放在 `tools/`，因为本地工具和 MCP 工具都应该通过统一工具系统暴露给 Agent。这样讲起来更清楚：Gateway 负责“谁来处理”，Agent 负责“怎么思考和执行”，Tools/Application 负责“具体做事”。

## 当前状态

已完成最小 Zulip + 意图路由 + Todo 持久化闭环：

```text
Zulip @Jarvis
  -> traceforge.interfaces.zulip.bridge
  -> POST /api/events/zulip
  -> WorkspaceEvent
  -> Context Builder
  -> Session Resolver
  -> WorkspaceGateway
  -> AgentRuntime / Application
  -> todo.* / memory.* Tool
  -> TodoWorkflow / SQLite
  -> Jarvis 回帖到同一 Topic
```

Gitea 出事喊一声（第一期，不经 AgentRuntime）：

```text
Gitea Webhook
  -> POST /api/events/gitea
  -> normalize + audit JSONL
  -> RepoAudit Zulip API → stream/topic（默认 general / gitea）
```

第一个里程碑是 Topic 感知的 Todo Agent：

```text
Zulip message -> WorkspaceEvent -> Intent Router -> todo.* Tool -> TodoWorkflow -> Repository -> Evidence-based reply
```

本地运行默认使用 `.traceforge/traceforge.sqlite3`，表结构包括：

- `traceforge_todos`
- `traceforge_todo_events`
- `traceforge_sessions`
- `memory_md_chunks` / `memory_md_fts` / `memory_md_embeddings`（与主库同文件或独立 mem db，由部署决定）

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,server,memory]"
pytest
```

### 本地 Embedding（无需 OpenAI Key）

默认使用 `fastembed` + `BAAI/bge-small-zh-v1.5`，首次会自动下载到 `.traceforge/models/embeddings/`：

```bash
pip install -e ".[memory]"
python -m traceforge.memory.download_embedding
```

对应 OpenClaw 的 `memorySearch.provider = local`；TraceForge 用 Python ONNX 模型，不用 node-llama-cpp GGUF。

## 最小服务

```bash
python -m uvicorn traceforge.server:app --host 0.0.0.0 --port 19090
```

健康检查：

```bash
curl http://127.0.0.1:19090/health
```

模拟一条 Zulip 事件：

```bash
PYTHONPATH=src python scripts/smoke_zulip_event.py
```

## Zulip Bridge

当前阶段 bridge 作为 TraceForge 项目内的 Zulip Adapter 运行，不单独容器化。

启动方式：

```bash
python scripts/run_zulip_bridge.py
```

前置条件：

- `traceforge-app` 正在运行
- 独立 TraceForge Zulip 正在运行
- `.env` 中配置了 `TRACEFORGE_ZULIP_*`
- `.env` 中配置了 `DEEPSEEK_API_KEY`

## Docker 部署

新服务器从零部署请看：

- [新服务器从零部署 TraceForge](docs/deployment/FRESH_SERVER_DEPLOYMENT.md)

项目使用 Docker Compose 显式声明 PostgreSQL、Redis、Zulip 等基础镜像来源；TraceForge API 镜像由本仓库 `Dockerfile` 构建。
