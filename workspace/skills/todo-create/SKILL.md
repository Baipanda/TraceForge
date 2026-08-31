---
name: todo-create
description: 当用户要求创建、发布或记录 Todo 时使用
allowed-tools:
  - people.resolve
  - todo.create
  - zulip.reply
---

# 创建 Todo

## 必填

1. **标题**
2. **负责人**（`assignee_name` / `assignee_email`；不明时先 `people.resolve`）
3. **组织树 subtree**

## subtree 怎么传

按优先级：

1. **只写 L3 名**（推荐日常用法）：`subtree_name=TraceForge Agent` 或新叶子名 `EMI专项`
   - 若库里已有该节点：按 `parent_id` 向上补全 L1/L2 路径
   - 若是新名字且当前 Topic 有默认映射：自动挂到该 Topic 默认节点的父级（L2）下，L1/L2 由父链补齐
2. **完整路径**：`subtree_path=硬件/主控板/EMI测试`（缺的 L2/L3 会创建；L1 必须已存在）
3. **code**：`subtree_code=software.cloud.agent`
4. 已知 Topic（agent开发 / football 等）也可自动匹配默认节点

## 处理流程

1. 提取标题、负责人、subtree（及可选 description）。
2. 负责人不明确时调用 `people.resolve`。
3. 调用 `todo.create`。
4. **直接使用工具返回的 `reply_text`**（固定表格：已创建 Todo）。

## 约束

- 不要假装已写入数据库。
- description 可选；列表默认不展示描述。
