#!/usr/bin/env python3
"""Seed Project Admin + lightweight TraceForge todos for progress-sop demo (todo-show)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("TRACEFORGE_PROJECT_ADMIN_URL", "http://127.0.0.1:18081").rstrip("/")
MENTOR = os.environ.get("TRACEFORGE_PROJECT_ADMIN_MENTOR", "traceforge-admin")
DB = Path(os.environ.get("TRACEFORGE_DB_PATH", str(ROOT / ".traceforge" / "traceforge.sqlite3")))


class HttpError(RuntimeError):
    def __init__(self, code: int, path: str, detail: str) -> None:
        super().__init__(f"HTTP {code} {path}: {detail}")
        self.code = code


def _req(method: str, path: str, payload: dict | None = None, *, mentor: bool = False) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if mentor:
        headers["X-Mentor"] = MENTOR
    request = urllib.request.Request(ADMIN_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, path, detail) from exc


def seed_project() -> dict:
    existing = None
    try:
        existing = _req("GET", "/api/projects/todo-show")
    except HttpError as exc:
        if exc.code != 404:
            raise
        existing = None
    body = {
        "project_id": "todo-show",
        "display_name": "Todo Show 开发",
        "description": "progress-sop 演示样例：对照 references/todo-show",
        "status": "active",
        "zulip_stream": "sandbox",
        "zulip_topic": "todo-show开发",
        "docs_root": "workspace_shared/docs/todo-show",
        "prd_path": "PRD.md",
        "tech_path": "TECH.md",
        "gitea_owner": "traceforge",
        "gitea_repo": "TraceForge",
        "default_branch": "main",
        "path_filters": ["references/todo-show/"],
        "subtree_code": "software.cloud.agent",
        "window_days": 7,
    }
    if existing and existing.get("project_id") == "todo-show":
        project = _req("PUT", "/api/projects/todo-show", body, mentor=True)
        print("updated project todo-show")
    else:
        project = _req("POST", "/api/projects", body, mentor=True)
        print("created project todo-show")

    # reset members then add demo owners
    for member in list(project.get("members") or []):
        mid = member.get("id")
        if mid is not None:
            try:
                _req("DELETE", f"/api/projects/todo-show/members/{mid}", mentor=True)
            except HttpError:
                pass
    for person_name, role in (("traceforge-admin", "owner"), ("Bai", "dev"), ("Neymar", "dev")):
        _req(
            "POST",
            "/api/projects/todo-show/members",
            {"person_name": person_name, "role": role},
            mentor=True,
        )
        print(f"member {person_name} ({role})")
    return _req("GET", "/api/projects/todo-show")


def seed_todos() -> None:
    if not DB.exists():
        print(f"skip todos: db missing {DB}")
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # ensure subtree exists
    row = conn.execute(
        "SELECT id FROM org_subtrees WHERE code = ? LIMIT 1",
        ("software.cloud.agent",),
    ).fetchone()
    if not row:
        print("skip todos: subtree software.cloud.agent not found")
        conn.close()
        return
    subtree_id = row["id"]
    now = datetime.now(timezone.utc).isoformat()
    samples = [
        ("完善 Todo 父子占比滚动", "in_progress", "Bai"),
        ("补齐 Bug 标记与列表筛选", "open", "Neymar"),
        ("Zulip Topic 回链验收", "open", "Bai"),
        ("操作日志字段对齐 USER_GUIDE", "done", "Neymar"),
    ]
    for title, status, assignee in samples:
        exists = conn.execute(
            "SELECT id FROM traceforge_todos WHERE title = ? AND deleted_at IS NULL LIMIT 1",
            (title,),
        ).fetchone()
        if exists:
            continue
        todo_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO traceforge_todos (
                id, title, description, status, priority, workspace_id, subtree_id,
                channel_name, topic, proposer_name, proposer_email,
                assignee_name, assignee_email, source_message_id,
                created_at, updated_at, completed_at, deleted_at
            ) VALUES (?, ?, ?, ?, 0, 'default', ?, 'sandbox', 'todo-show开发',
                      'traceforge-admin', '', ?, '', NULL, ?, ?, ?, NULL)
            """,
            (
                todo_id,
                title,
                "seeded for progress-sop",
                status,
                subtree_id,
                assignee,
                now,
                now,
                now if status == "done" else None,
            ),
        )
        print(f"todo {title}")
    conn.commit()
    conn.close()


def main() -> None:
    print(f"Project Admin: {ADMIN_URL}")
    project = seed_project()
    seed_todos()
    print(json.dumps({"project_id": project.get("project_id"), "members": project.get("members")}, ensure_ascii=False, indent=2))
    print("fixture ready. Try: @Jarvis 项目进度：todo-show")


if __name__ == "__main__":
    main()
