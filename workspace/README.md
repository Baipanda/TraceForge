# TraceForge Agent Workspace

这里是 Agent 的可读工作区，借鉴 OpenClaw 的 workspace 组织方式。

## 文件职责

- `AGENTS.md`：全局行为和安全约定
- `IDENTITY.md`：Jarvis 身份、语气和能力边界
- `TOOLS.md`：本地 Tool / MCP Tool 的调用约定
- `MEMORY.md`：长期上下文入口，不存放密钥
- `skills/`：面向具体任务的流程说明
- `scripts/`：开发和运维辅助脚本

Workspace 文件可以被 Harness 加载并组装进模型上下文，但不能绕过 Domain、Application 或 Tool 的安全边界。
