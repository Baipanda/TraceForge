---
name: progress-sop
description: 当用户要求项目进度体检、进度 SOP、progress sop 时使用
allowed-tools:
  - project.resolve
  - project.get
  - topic.summarize
  - todo.list
  - todo.summary
  - todo.create
  - zulip.send_choices
  - agent.send
  - fs.read
---

# progress-sop

固定流水线名：**progress-sop**（代码编排器优先拦截；本 Skill 作为模型侧说明书）。

## 触发

```text
@Jarvis 项目进度：todo-show
@Jarvis 进度体检：todo-show
```

## 步骤

1. **Scope**：必须用 `project.resolve` / Project Admin **查库**，禁止猜绑定。
2. **HITL-A**：`zulip.send_choices`（zform）确认窗口 / 是否 Audit / 侧重点。
3. **Docs**：读 `workspace_shared` 下项目文档。
4. **Discussion**：Topic 摘要。
5. **Tasks**：Todo list/summary。
6. **Audit（A2A）**：`agent.send` → `gitea-audit`。RepoAudit **只审不写代码**。
7. **Report**：汇总回 Zulip。
8. **HITL-B**：zform 选择仅阅览 / 建 Todo / 记 DECISION。

## zform 约定

- 需要用户做离散选择时，必须用 `zulip.send_choices`，不要只发纯文字。
- choice 的 `reply` 应带 `@Jarvis`，以便 Bridge 收到点击回调。

## 禁止

- 不要让 gitea-audit / RepoAudit 写业务代码或开 PR。
- Scope 失败时提示去 Project Admin 补项目名片，不要编造 stream/repo。
