"""FastAPI application — Todo Show API."""
from __future__ import annotations

import math
import uuid
from calendar import monthrange
from datetime import datetime, timezone
from datetime import timedelta
from typing import Optional
from urllib.parse import unquote
from uuid import UUID

import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from database import execute, query, query_one, transaction
from schemas import (
    ChildWeightsUpdate,
    DEFAULT_PROGRESS_PROMPT,
    TODO_PRIORITIES,
    TODO_STATUSES,
    TODO_SYNC_FREQUENCIES,
    LogEntryOut,
    PaginatedResponse,
    PersonOut,
    ProgressCreate,
    ProgressCreateResponse,
    ProgressEntryOut,
    ProjectOut,
    StatsOut,
    SubtreeOut,
    SyncStatusOut,
    TodoCreate,
    TodoDetailOut,
    TodoListOut,
    TodoUpdate,
)

app = FastAPI(title="Todo Show API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def apply_database_migrations():
    from apply_migrations import main as apply_migrations

    try:
        apply_migrations()
        summary = reconcile_parent_rollups_once()
        if summary is not None:
            print(f"Parent Todo rollups reconciled: {summary}")
    except Exception as exc:
        print(f"WARNING: database migrations were not applied: {exc}")


# ── Helpers ────────────────────────────────────────────────────────

def _parse_pg_array(val) -> list:
    """Parse a PostgreSQL array literal into a Python list."""
    if isinstance(val, list):
        return val
    if val is None or val == "{}" or val == "":
        return []
    s = str(val).strip("{}")
    if not s:
        return []
    return [x.strip('"') for x in s.split(",")]


def _names(ids) -> list[str]:
    """Resolve people IDs to canonical names, preserving input order."""
    ids = _parse_pg_array(ids)
    if not ids:
        return []
    # Build a lookup map to preserve original order
    rows = query(
        "SELECT id, canonical_name FROM people WHERE id = ANY(%s)",
        (ids,),
    )
    lookup = {r["id"]: r["canonical_name"] for r in rows}
    return [lookup[i] for i in ids if i in lookup]


SYNC_FREQUENCY_LABELS = {
    "daily": "每天",
    "every_3_days": "每 3 天",
    "weekly": "每周",
    "biweekly": "每两周",
    "monthly": "每月",
}

APP_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
SYNC_DUE_FILTERS = {
    "needs_today",
    "filled_today",
    "synced_today",
    "overdue",
    "due_today",
    "next_3_days",
    "next_7_days",
    "not_configured",
}


def _sync_day_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(APP_TIMEZONE)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return today_start.astimezone(timezone.utc), tomorrow_start.astimezone(timezone.utc)


def _add_sync_interval(value: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return value + timedelta(days=1)
    if frequency == "every_3_days":
        return value + timedelta(days=3)
    if frequency == "weekly":
        return value + timedelta(days=7)
    if frequency == "biweekly":
        return value + timedelta(days=14)
    if frequency == "monthly":
        year = value.year + (1 if value.month == 12 else 0)
        month = 1 if value.month == 12 else value.month + 1
        day = min(value.day, monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)
    raise ValueError(f"Unsupported sync frequency: {frequency}")


def _duration_hint(delta: timedelta) -> str:
    seconds = max(0, int(abs(delta.total_seconds())))
    if seconds < 3600:
        return f"{max(1, math.ceil(seconds / 60))} 分钟"
    if seconds < 86400:
        return f"{math.ceil(seconds / 3600)} 小时"
    return f"{math.ceil(seconds / 86400)} 天"


def _build_sync_info(
    todo_status: str,
    frequency: Optional[str],
    created_at: datetime,
    last_progress_at: Optional[datetime],
    last_progress_confirmed_at: Optional[datetime] = None,
    last_confirmed_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
    last_progress_source: str = "manual",
) -> tuple[Optional[datetime], SyncStatusOut]:
    if todo_status != "pending":
        status_labels = {
            "completed": "已完成",
            "cancelled": "已取消",
            "expired": "已过期",
        }
        label = status_labels.get(todo_status, "已结束")
        return None, SyncStatusOut(
            code="closed",
            label="已结束",
            hint=f"Todo {label}，无需继续同步",
            tone="secondary",
        )

    now = now or datetime.now(timezone.utc)
    today_start, tomorrow_start = _sync_day_bounds(now)

    if last_progress_at and last_progress_confirmed_at is None:
        recorded_today = today_start <= last_progress_at < tomorrow_start
        next_sync_at = (
            _add_sync_interval(last_confirmed_at or created_at, frequency)
            if frequency in TODO_SYNC_FREQUENCIES
            else None
        )
        confirmation_overdue = (
            not recorded_today
            and next_sync_at is not None
            and next_sync_at < today_start
        )
        if confirmation_overdue:
            planned_date = next_sync_at.astimezone(APP_TIMEZONE).strftime("%Y-%m-%d")
            return next_sync_at, SyncStatusOut(
                code="pending_confirmation_overdue",
                label="待确认（已逾期）",
                hint=f"进展尚未确认；计划同步日期：{planned_date}",
                tone="danger",
            )
        return next_sync_at, SyncStatusOut(
            code="filled_today" if recorded_today else "pending_confirmation",
            label="今日已填写" if recorded_today else "待确认",
            hint="进展已填写，确认后才会完成本次同步",
            tone="info" if recorded_today else "warning",
        )

    if last_confirmed_at and today_start <= last_confirmed_at < tomorrow_start:
        next_sync_at = (
            _add_sync_interval(last_confirmed_at, frequency)
            if frequency in TODO_SYNC_FREQUENCIES
            else None
        )
        next_sync_hint = (
            f"，下次同步：{next_sync_at.astimezone(APP_TIMEZONE).strftime('%Y-%m-%d')}"
            if next_sync_at
            else ""
        )
        return next_sync_at, SyncStatusOut(
            code="synced_today",
            label="今日已同步",
            hint=(
                f"所有处理中子 Todo 今日均已同步，系统自动汇总{next_sync_hint}"
                if last_progress_source == "children_rollup"
                else f"本次同步已确认{next_sync_hint}"
            ),
            tone="success",
        )

    if frequency not in TODO_SYNC_FREQUENCIES:
        return None, SyncStatusOut(
            code="not_configured",
            label="未设置",
            hint="尚未设置同步频率",
            tone="secondary",
        )

    next_sync_at = _add_sync_interval(last_confirmed_at or created_at, frequency)
    next_sync_date = next_sync_at.astimezone(APP_TIMEZONE).strftime("%Y-%m-%d")

    if next_sync_at < today_start:
        meta = SyncStatusOut(
            code="overdue",
            label="已逾期",
            hint=f"计划同步日期：{next_sync_date}",
            tone="danger",
        )
    elif next_sync_at < tomorrow_start:
        meta = SyncStatusOut(
            code="due_today",
            label="今日待同步",
            hint="今天需要填写同步进展",
            tone="warning",
        )
    else:
        meta = SyncStatusOut(
            code="scheduled",
            label="计划中",
            hint=f"下次同步：{next_sync_date}",
            tone="info",
        )
    return next_sync_at, meta


def _normalize_sync_frequency(value: Optional[str]) -> Optional[str]:
    value = value.strip() if value else None
    if value is not None and value not in TODO_SYNC_FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"Invalid sync frequency: {value}")
    return value


def _build_todo_list_item(row: dict) -> TodoListOut:
    next_sync_at, status_meta = _build_sync_info(
        row["status"],
        row.get("track_frequency"),
        row["created_at"],
        row.get("last_progress_at"),
        row.get("last_progress_confirmed_at"),
        row.get("last_confirmed_at"),
        last_progress_source=row.get("last_progress_source") or "manual",
    )
    return TodoListOut(
        id=row["id"],
        title=row["title"],
        is_bug=bool(row.get("is_bug")),
        status=row["status"],
        priority=row["priority"],
        main_force_names=row.get("main_force_names") or [],
        process_manager_names=row.get("process_manager_names") or [],
        subtree_name=row.get("subtree_name", ""),
        project_name=row.get("project_name"),
        parent_id=row.get("parent_id"),
        parent_title=row.get("parent_title"),
        auto_completed_by_children=bool(row.get("auto_completed_by_children")),
        track_frequency=row.get("track_frequency"),
        track_frequency_label=SYNC_FREQUENCY_LABELS.get(row.get("track_frequency")),
        progress_prompt=row.get("progress_prompt") or DEFAULT_PROGRESS_PROMPT,
        last_progress_id=row.get("last_progress_id"),
        last_progress_at=row.get("last_progress_at"),
        last_progress_confirmed_at=row.get("last_progress_confirmed_at"),
        last_progress_source=row.get("last_progress_source") or "manual",
        last_confirmed_at=row.get("last_confirmed_at"),
        next_sync_at=next_sync_at,
        sync_status=status_meta.code,
        status_meta=status_meta,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _build_todo_detail(row: dict) -> TodoDetailOut:
    tid = row["id"]

    children_rows = query(
        """SELECT id, title, is_bug, status, priority, parent_weight_percent FROM todos
           WHERE parent_id = %s AND deleted_at IS NULL
           ORDER BY created_at ASC, id ASC""",
        (tid,),
    )
    children = [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "is_bug": bool(r.get("is_bug")),
            "status": r["status"],
            "priority": r["priority"],
            "parent_weight_percent": r.get("parent_weight_percent") or 0,
        }
        for r in children_rows
    ]

    parent_title = None
    if row.get("parent_id"):
        p = query_one(
            "SELECT title FROM todos WHERE id = %s AND deleted_at IS NULL",
            (row["parent_id"],),
        )
        if p:
            parent_title = p["title"]

    depends_details = []
    dep_ids = _parse_pg_array(row.get("depends_on_ids"))
    if dep_ids:
        deps = query(
            "SELECT id, title, status FROM todos WHERE id = ANY(%s) AND deleted_at IS NULL",
            (dep_ids,),
        )
        depends_details = [
            {"id": str(d["id"]), "title": d["title"], "status": d["status"]}
            for d in deps
        ]

    next_sync_at, status_meta = _build_sync_info(
        row["status"],
        row.get("track_frequency"),
        row["created_at"],
        row.get("last_progress_at"),
        row.get("last_progress_confirmed_at"),
        row.get("last_confirmed_at"),
        last_progress_source=row.get("last_progress_source") or "manual",
    )

    return TodoDetailOut(
        id=row["id"],
        title=row["title"],
        is_bug=bool(row.get("is_bug")),
        description=row.get("description"),
        status=row["status"],
        priority=row["priority"],
        proposer_id=row["proposer_id"],
        proposer_name=row.get("proposer_name", ""),
        tracker_id=row.get("tracker_id"),
        tracker_name=row.get("tracker_name"),
        project_id=row.get("project_id"),
        project_name=row.get("project_name"),
        subtree_id=row["subtree_id"],
        subtree_name=row.get("subtree_name", ""),
        zulip_stream=row.get("zulip_stream"),
        zulip_topic=row.get("zulip_topic"),
        source_message_id=row.get("source_message_id"),
        completed_at=row.get("completed_at"),
        auto_completed_by_children=bool(row.get("auto_completed_by_children")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row.get("deleted_at"),
        track_frequency=row.get("track_frequency"),
        track_frequency_label=SYNC_FREQUENCY_LABELS.get(row.get("track_frequency")),
        progress_prompt=row.get("progress_prompt") or DEFAULT_PROGRESS_PROMPT,
        last_progress_content=row.get("last_progress_content"),
        last_progress_id=row.get("last_progress_id"),
        last_progress_at=row.get("last_progress_at"),
        last_progress_confirmed_at=row.get("last_progress_confirmed_at"),
        last_progress_source=row.get("last_progress_source") or "manual",
        last_confirmed_at=row.get("last_confirmed_at"),
        next_sync_at=next_sync_at,
        sync_status=status_meta.code,
        status_meta=status_meta,
        depends_on_ids=_parse_pg_array(row.get("depends_on_ids")),
        depends_on_details=depends_details,
        parent_id=row.get("parent_id"),
        parent_title=parent_title,
        parent_weight_percent=row.get("parent_weight_percent"),
        children=children,
        watcher_ids=_parse_pg_array(row.get("watcher_ids")),
        watcher_names=_names(row.get("watcher_ids")),
        process_manager_ids=_parse_pg_array(row.get("process_manager_ids")),
        process_manager_names=_names(row.get("process_manager_ids")),
        technical_advisor_ids=_parse_pg_array(row.get("technical_advisor_ids")),
        technical_advisor_names=_names(row.get("technical_advisor_ids")),
        main_force_ids=_parse_pg_array(row.get("main_force_ids")),
        main_force_names=_names(row.get("main_force_ids")),
        backup_force_ids=_parse_pg_array(row.get("backup_force_ids")),
        backup_force_names=_names(row.get("backup_force_ids")),
        image_paths=_parse_pg_array(row.get("image_paths")),
    )


# ── Logging ──────────────────────────────────────────────────────

LOG_ACTIONS = {
    "created",
    "updated",
    "completed",
    "cancelled",
    "deleted",
    "progress_filled",
    "progress_confirmed",
    "auto_completed",
    "auto_reopened",
    "sync_auto_confirmed",
    "sync_rollup_revoked",
    "weights_updated",
}

LOG_FIELD_LABELS = {
    "title": "标题",
    "is_bug": "Bug 标记",
    "description": "描述",
    "status": "状态",
    "priority": "优先级",
    "subtree_id": "分类",
    "project_id": "项目",
    "tracker_id": "跟踪人",
    "parent_id": "父 Todo",
    "depends_on_ids": "依赖项",
    "watcher_ids": "关注人",
    "process_manager_ids": "流程管理",
    "technical_advisor_ids": "技术顾问",
    "main_force_ids": "主力",
    "backup_force_ids": "后备力量",
    "track_frequency": "同步频率",
    "progress_prompt": "进展填写提示",
    "zulip_stream": "Zulip Stream",
    "zulip_topic": "Zulip Topic",
    "image_paths": "图片路径",
    "completed_at": "完成时间",
    "parent_weight_percent": "子项占比",
}

_LOG_SCHEMA_READY = False


def _ensure_operation_log_schema(cur):
    global _LOG_SCHEMA_READY
    if _LOG_SCHEMA_READY:
        return
    cur.execute(
        """CREATE TABLE IF NOT EXISTS operation_logs (
               id BIGSERIAL PRIMARY KEY,
               username TEXT NOT NULL,
               action TEXT NOT NULL,
               target_type TEXT NOT NULL,
               target_id TEXT,
               detail TEXT,
               created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
           )"""
    )
    cur.execute("ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS changes JSONB")
    _LOG_SCHEMA_READY = True


def _log(
    username: str,
    action: str,
    target_type: str,
    target_id: str,
    detail: str = None,
    changes: dict | None = None,
    cur=None,
):
    """Insert an operation log entry."""
    if not username:
        username = "anonymous"
    sql = """INSERT INTO operation_logs (username, action, target_type, target_id, detail, changes)
             VALUES (%s, %s, %s, %s, %s, %s)"""
    params = (
        username,
        action,
        target_type,
        target_id,
        detail,
        psycopg2.extras.Json(changes) if changes is not None else None,
    )
    if cur is not None:
        _ensure_operation_log_schema(cur)
        cur.execute(sql, params)
    else:
        with transaction() as conn:
            with conn.cursor() as inner_cur:
                _ensure_operation_log_schema(inner_cur)
                inner_cur.execute(sql, params)


def _require_username(request: Request) -> str:
    username = (request.headers.get("X-User") or request.headers.get("x-user") or "").strip()
    if request.headers.get("X-User-Encoded") == "uri":
        username = unquote(username).strip()
    if not username:
        username = "unknown"
    return username


def _resolve_person(cur, username: str) -> dict:
    cur.execute(
        """SELECT p.id, p.canonical_name
           FROM people p
           LEFT JOIN person_aliases pa ON pa.person_id = p.id
           WHERE LOWER(p.canonical_name) = LOWER(%s)
              OR LOWER(pa.alias) = LOWER(%s)
           ORDER BY CASE WHEN LOWER(p.canonical_name) = LOWER(%s) THEN 0 ELSE 1 END,
                    p.id
           LIMIT 1""",
        (username, username, username),
    )
    person = cur.fetchone()
    if not person:
        raise HTTPException(status_code=400, detail=f"当前用户未关联人员信息：{username}")
    return person


def _normalize_log_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return [_normalize_log_value(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize_log_value(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _log_value_text(value) -> str:
    value = _normalize_log_value(value)
    if value is None or value == "":
        return "空"
    if isinstance(value, list):
        if not value:
            return "空"
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def _build_change_detail(before: dict, requested: dict, auto_changes: dict | None = None) -> str:
    changes = []
    payload = _build_change_payload(before, requested, auto_changes)

    for field, change in payload.items():
        label = LOG_FIELD_LABELS.get(field, field)
        changes.append(f"{label}: {_log_value_text(change['old'])} -> {_log_value_text(change['new'])}")

    if not changes:
        return "无实际字段变化"
    return "修改字段；" + "；".join(changes)


def _build_change_payload(before: dict, requested: dict, auto_changes: dict | None = None) -> dict:
    changes = {}
    all_changes = dict(requested)
    if auto_changes:
        all_changes.update(auto_changes)

    for field, new_value in all_changes.items():
        old_value = before.get(field)
        old_norm = _normalize_log_value(_parse_pg_array(old_value) if field.endswith("_ids") or field == "image_paths" else old_value)
        new_norm = _normalize_log_value(new_value)
        if old_norm == new_norm:
            continue

        label = LOG_FIELD_LABELS.get(field, field)
        changes[field] = {"label": label, "old": old_norm, "new": new_norm}

    return changes


def _fetch_one(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    return cur.fetchone()


def _ensure_exists(cur, table: str, value, label: str, deleted_filter: bool = False):
    if value is None:
        return
    sql = f"SELECT id FROM {table} WHERE id = %s"
    if deleted_filter:
        sql += " AND deleted_at IS NULL"
    if not _fetch_one(cur, sql, (value,)):
        raise HTTPException(status_code=400, detail=f"{label} not found: {value}")


def _ensure_people_exist(cur, ids: list[int], label: str):
    ids = [i for i in ids if i is not None]
    if not ids:
        return
    cur.execute("SELECT id FROM people WHERE id = ANY(%s)", (ids,))
    existing = {r["id"] for r in cur.fetchall()}
    missing = [str(i) for i in ids if i not in existing]
    if missing:
        raise HTTPException(status_code=400, detail=f"{label} not found: {', '.join(missing)}")


def _ensure_todos_exist(cur, ids: list[UUID], label: str):
    ids = [uuid.UUID(str(i)) for i in ids if i is not None]
    if not ids:
        return
    cur.execute("SELECT id FROM todos WHERE id = ANY(%s) AND deleted_at IS NULL", (ids,))
    existing = {str(r["id"]) for r in cur.fetchall()}
    missing = [str(i) for i in ids if str(i) not in existing]
    if missing:
        raise HTTPException(status_code=400, detail=f"{label} not found: {', '.join(missing)}")


def _ensure_dependencies_completed(cur, todo_id: UUID, depends_on_ids) -> None:
    dep_ids = _parse_pg_array(depends_on_ids)
    if not dep_ids:
        return

    cur.execute(
        """SELECT id, title, status
           FROM todos
           WHERE id = ANY(%s)
             AND deleted_at IS NULL
             AND status <> 'completed'
           ORDER BY updated_at DESC
           LIMIT 10""",
        ([uuid.UUID(str(dep_id)) for dep_id in dep_ids],),
    )
    unfinished = cur.fetchall()
    if not unfinished:
        return

    items = [
        f"{row['title']} ({row['status']})"
        for row in unfinished
    ]
    raise HTTPException(
        status_code=400,
        detail="无法完成 Todo：存在未完成的依赖项：" + "；".join(items),
    )


def _dependencies_are_completed(cur, depends_on_ids) -> bool:
    dep_ids = _parse_pg_array(depends_on_ids)
    if not dep_ids:
        return True
    cur.execute(
        """SELECT 1
           FROM todos
           WHERE id = ANY(%s)
             AND deleted_at IS NULL
             AND status <> 'completed'
           LIMIT 1""",
        ([uuid.UUID(str(dep_id)) for dep_id in dep_ids],),
    )
    return cur.fetchone() is None


def _ensure_children_ended(cur, todo_id: UUID | str) -> None:
    unfinished = _fetch_one(
        cur,
        """SELECT COUNT(*) AS count
           FROM todos
           WHERE parent_id = %s
             AND deleted_at IS NULL
             AND status = 'pending'""",
        (str(todo_id),),
    )["count"]
    if unfinished:
        raise HTTPException(
            status_code=400,
            detail=f"无法完成父 Todo：仍有 {unfinished} 个处理中子 Todo",
        )


def _parent_work_rollup_action(
    parent_status: str,
    auto_completed: bool,
    child_count: int,
    pending_count: int,
    child_weight_total: int,
    dependencies_completed: bool,
) -> str | None:
    fully_covered = child_weight_total == 100
    if child_count > 0 and pending_count == 0 and fully_covered:
        if parent_status == "pending" and dependencies_completed:
            return "complete"
        if parent_status == "completed" and auto_completed and not dependencies_completed:
            return "reopen"
        return None
    if (
        parent_status == "completed"
        and auto_completed
        and (pending_count > 0 or not fully_covered)
    ):
        return "reopen"
    return None


def _roll_up_parent_work_status(
    cur,
    parent_ids,
    username: str,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    queue = [str(parent_id) for parent_id in (parent_ids or []) if parent_id]
    visited: set[str] = set()
    result = {"completed": 0, "reopened": 0}

    while queue:
        parent_id = queue.pop(0)
        if parent_id in visited:
            continue
        visited.add(parent_id)
        parent = _fetch_one(
            cur,
            """SELECT id, title, status, parent_id, depends_on_ids,
                      auto_completed_by_children
               FROM todos
               WHERE id = %s AND deleted_at IS NULL
               FOR UPDATE""",
            (parent_id,),
        )
        if not parent:
            continue

        stats = _fetch_one(
            cur,
            """SELECT COUNT(*) AS child_count,
                      COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
                      COALESCE(SUM(parent_weight_percent), 0)::INTEGER AS child_weight_total
               FROM todos
               WHERE parent_id = %s AND deleted_at IS NULL""",
            (parent_id,),
        )
        dependencies_completed = _dependencies_are_completed(
            cur, parent.get("depends_on_ids")
        )
        action = _parent_work_rollup_action(
            parent["status"],
            bool(parent.get("auto_completed_by_children")),
            stats["child_count"],
            stats["pending_count"],
            stats["child_weight_total"],
            dependencies_completed,
        )

        if action == "complete":
            cur.execute(
                """UPDATE todos
                   SET status = 'completed', completed_at = %s, updated_at = %s,
                       auto_completed_by_children = TRUE
                   WHERE id = %s""",
                (now, now, parent_id),
            )
            _log(
                username,
                "auto_completed",
                "todo",
                parent_id,
                f"子 Todo 均已结束且占比合计 100%，自动完成父 Todo；标题: {parent['title'][:120]}",
                changes={
                    "status": {"label": "状态", "old": parent["status"], "new": "completed"},
                    "auto_completed_by_children": {
                        "label": "子项自动完成",
                        "old": bool(parent.get("auto_completed_by_children")),
                        "new": True,
                    },
                },
                cur=cur,
            )
            result["completed"] += 1
        elif action == "reopen":
            reasons = []
            if stats["pending_count"]:
                reasons.append(f"{stats['pending_count']} 个子 Todo 处理中")
            if stats["child_weight_total"] != 100:
                reasons.append(f"子 Todo 占比合计 {stats['child_weight_total']}%")
            if not dependencies_completed:
                reasons.append("存在未完成依赖")
            reason_text = "、".join(reasons) or "自动完成条件发生变化"
            cur.execute(
                """UPDATE todos
                   SET status = 'pending', completed_at = NULL, updated_at = %s,
                       auto_completed_by_children = FALSE
                   WHERE id = %s""",
                (now, parent_id),
            )
            _log(
                username,
                "auto_reopened",
                "todo",
                parent_id,
                f"{reason_text}，自动恢复父 Todo；标题: {parent['title'][:120]}",
                changes={
                    "status": {"label": "状态", "old": "completed", "new": "pending"},
                    "auto_completed_by_children": {
                        "label": "子项自动完成",
                        "old": True,
                        "new": False,
                    },
                },
                cur=cur,
            )
            result["reopened"] += 1

        if parent.get("parent_id"):
            queue.append(str(parent["parent_id"]))

    return result


def _parent_sync_rollup_action(
    parent_status: str,
    child_count: int,
    active_count: int,
    unsynced_count: int,
    already_synced_today: bool,
    has_active_rollup_today: bool,
) -> str | None:
    eligible = (
        parent_status == "pending"
        and child_count > 0
        and active_count > 0
        and unsynced_count == 0
    )
    if eligible and not already_synced_today:
        return "sync"
    if not eligible and has_active_rollup_today:
        return "revoke"
    return None


def _latest_child_sync_actor(cur, parent_id: str, today_start: datetime, tomorrow_start: datetime):
    return _fetch_one(
        cur,
        """SELECT h.confirmed_by AS id, p.canonical_name
           FROM todos child
           JOIN todo_progress_history h ON h.todo_id = child.id
           JOIN people p ON p.id = h.confirmed_by
           WHERE child.parent_id = %s
             AND child.deleted_at IS NULL
             AND h.confirmed_at >= %s AND h.confirmed_at < %s
             AND h.revoked_at IS NULL
           ORDER BY h.confirmed_at DESC
           LIMIT 1""",
        (parent_id, today_start, tomorrow_start),
    )


def _roll_up_parent_sync_status(
    cur,
    parent_ids,
    username: str,
    actor: dict | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    today_start, tomorrow_start = _sync_day_bounds(now)
    queue = [str(parent_id) for parent_id in (parent_ids or []) if parent_id]
    visited: set[str] = set()
    result = {"synced": 0, "revoked": 0}

    while queue:
        parent_id = queue.pop(0)
        if parent_id in visited:
            continue
        visited.add(parent_id)
        parent = _fetch_one(
            cur,
            """SELECT id, title, status, parent_id
               FROM todos
               WHERE id = %s AND deleted_at IS NULL
               FOR UPDATE""",
            (parent_id,),
        )
        if not parent:
            continue

        child_stats = _fetch_one(
            cur,
            """SELECT COUNT(*) AS child_count,
                      COUNT(*) FILTER (WHERE child.status = 'pending') AS active_count,
                      COUNT(*) FILTER (
                          WHERE child.status = 'pending'
                            AND NOT (
                                latest.confirmed_at IS NOT NULL
                                AND confirmed.last_confirmed_at >= %s
                                AND confirmed.last_confirmed_at < %s
                            )
                      ) AS unsynced_count
               FROM todos child
               LEFT JOIN LATERAL (
                   SELECT h.confirmed_at
                   FROM todo_progress_history h
                   WHERE h.todo_id = child.id AND h.revoked_at IS NULL
                   ORDER BY h.recorded_at DESC,
                            (h.confirmed_at IS NULL) DESC,
                            h.id DESC
                   LIMIT 1
               ) latest ON TRUE
               LEFT JOIN LATERAL (
                   SELECT MAX(h.confirmed_at) AS last_confirmed_at
                   FROM todo_progress_history h
                   WHERE h.todo_id = child.id
                     AND h.confirmed_at IS NOT NULL
                     AND h.revoked_at IS NULL
               ) confirmed ON TRUE
               WHERE child.parent_id = %s AND child.deleted_at IS NULL""",
            (today_start, tomorrow_start, parent_id),
        )
        parent_sync = _fetch_one(
            cur,
            """SELECT
                   EXISTS (
                       SELECT 1
                       FROM todo_progress_history latest
                       WHERE latest.todo_id = %s
                         AND latest.revoked_at IS NULL
                         AND latest.confirmed_at IS NOT NULL
                         AND latest.confirmed_at >= %s
                         AND latest.confirmed_at < %s
                         AND latest.id = (
                             SELECT h.id
                             FROM todo_progress_history h
                             WHERE h.todo_id = %s AND h.revoked_at IS NULL
                             ORDER BY h.recorded_at DESC,
                                      (h.confirmed_at IS NULL) DESC,
                                      h.id DESC
                             LIMIT 1
                         )
                   ) AS already_synced_today,
                   EXISTS (
                       SELECT 1 FROM todo_progress_history h
                       WHERE h.todo_id = %s
                         AND h.source = 'children_rollup'
                         AND h.revoked_at IS NULL
                         AND h.confirmed_at >= %s AND h.confirmed_at < %s
                   ) AS has_active_rollup_today""",
            (
                parent_id, today_start, tomorrow_start, parent_id,
                parent_id, today_start, tomorrow_start,
            ),
        )
        action = _parent_sync_rollup_action(
            parent["status"],
            child_stats["child_count"],
            child_stats["active_count"],
            child_stats["unsynced_count"],
            parent_sync["already_synced_today"],
            parent_sync["has_active_rollup_today"],
        )

        if action == "sync":
            rollup_actor = actor or _latest_child_sync_actor(
                cur, parent_id, today_start, tomorrow_start
            )
            if rollup_actor:
                content = (
                    f"所有处理中子 Todo 今日均已完成同步确认"
                    f"（{child_stats['active_count']} 项），系统自动汇总。"
                )
                cur.execute(
                    """INSERT INTO todo_progress_history
                           (todo_id, content, recorded_at, recorded_by,
                            confirmed_at, confirmed_by, source)
                       VALUES (%s, %s, %s, %s, %s, %s, 'children_rollup')""",
                    (
                        parent_id, content, now, rollup_actor["id"],
                        now, rollup_actor["id"],
                    ),
                )
                cur.execute("UPDATE todos SET updated_at = %s WHERE id = %s", (now, parent_id))
                _log(
                    username,
                    "sync_auto_confirmed",
                    "todo",
                    parent_id,
                    f"子 Todo 今日均已同步，自动确认父 Todo；标题: {parent['title'][:120]}",
                    changes={
                        "sync_rollup": {
                            "label": "子项同步汇总",
                            "old": None,
                            "new": content,
                        }
                    },
                    cur=cur,
                )
                result["synced"] += 1
        elif action == "revoke":
            cur.execute(
                """UPDATE todo_progress_history
                   SET revoked_at = %s
                   WHERE todo_id = %s
                     AND source = 'children_rollup'
                     AND revoked_at IS NULL
                     AND confirmed_at >= %s AND confirmed_at < %s
                   RETURNING id""",
                (now, parent_id, today_start, tomorrow_start),
            )
            revoked = cur.fetchall()
            if revoked:
                cur.execute("UPDATE todos SET updated_at = %s WHERE id = %s", (now, parent_id))
                _log(
                    username,
                    "sync_rollup_revoked",
                    "todo",
                    parent_id,
                    f"子 Todo 同步条件已变化，父 Todo 自动汇总失效；标题: {parent['title'][:120]}",
                    changes={
                        "sync_rollup": {
                            "label": "子项同步汇总",
                            "old": "今日已同步",
                            "new": "已失效",
                        }
                    },
                    cur=cur,
                )
                result["revoked"] += len(revoked)

        if parent.get("parent_id"):
            queue.append(str(parent["parent_id"]))

    return result


def recalculate_parent_rollups(username: str = "system") -> dict[str, int]:
    totals = {"completed": 0, "reopened": 0, "synced": 0, "revoked": 0}
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, parent_id
                   FROM todos
                   WHERE deleted_at IS NULL"""
            )
            rows = cur.fetchall()
            parent_by_id = {
                str(row["id"]): str(row["parent_id"]) if row["parent_id"] else None
                for row in rows
            }
            parent_ids = {parent_id for parent_id in parent_by_id.values() if parent_id}

            def hierarchy_depth(todo_id: str) -> int:
                depth = 0
                current = todo_id
                seen: set[str] = set()
                while parent_by_id.get(current) and current not in seen:
                    seen.add(current)
                    current = parent_by_id[current]
                    depth += 1
                return depth

            deepest_first = sorted(parent_ids, key=hierarchy_depth, reverse=True)
            work_result = _roll_up_parent_work_status(cur, deepest_first, username)
            sync_result = _roll_up_parent_sync_status(cur, deepest_first, username)
            for result in (work_result, sync_result):
                for key, value in result.items():
                    totals[key] += value
    return totals


ROLLUP_RECONCILIATION_VERSION = "005_parent_rollups_reconciled"


def mark_parent_rollups_reconciled() -> None:
    execute(
        """INSERT INTO schema_migrations (version)
           VALUES (%s)
           ON CONFLICT (version) DO NOTHING""",
        (ROLLUP_RECONCILIATION_VERSION,),
    )


def reconcile_parent_rollups_once() -> dict[str, int] | None:
    applied = query_one(
        "SELECT 1 AS applied FROM schema_migrations WHERE version = %s",
        (ROLLUP_RECONCILIATION_VERSION,),
    )
    if applied:
        return None
    result = recalculate_parent_rollups()
    mark_parent_rollups_reconciled()
    return result


def _todo_ids_depending_on(cur, todo_id: UUID | str) -> list[str]:
    cur.execute(
        """SELECT id
           FROM todos
           WHERE %s = ANY(depends_on_ids)
             AND deleted_at IS NULL""",
        (uuid.UUID(str(todo_id)),),
    )
    return [str(row["id"]) for row in cur.fetchall()]


def _remaining_parent_weight(cur, parent_id: UUID | str) -> int:
    parent = _fetch_one(
        cur,
        """SELECT id
           FROM todos
           WHERE id = %s AND deleted_at IS NULL
           FOR UPDATE""",
        (str(parent_id),),
    )
    if not parent:
        raise HTTPException(status_code=400, detail="Parent todo not found")
    total = _fetch_one(
        cur,
        """SELECT COALESCE(SUM(parent_weight_percent), 0)::INTEGER AS total
           FROM todos
           WHERE parent_id = %s AND deleted_at IS NULL""",
        (str(parent_id),),
    )["total"]
    return max(0, 100 - total)


def _ensure_parent_allowed(cur, todo_id: UUID | None, parent_id: UUID | None):
    if parent_id is None:
        return
    _ensure_exists(cur, "todos", str(parent_id), "Parent todo", deleted_filter=True)
    if todo_id is None:
        return
    if str(todo_id) == str(parent_id):
        raise HTTPException(status_code=400, detail="Parent todo cannot be itself")
    cur.execute(
        """WITH RECURSIVE descendants AS (
               SELECT id FROM todos WHERE parent_id = %s AND deleted_at IS NULL
               UNION ALL
               SELECT t.id FROM todos t
               JOIN descendants d ON t.parent_id = d.id
               WHERE t.deleted_at IS NULL
           )
           SELECT id FROM descendants WHERE id = %s LIMIT 1""",
        (str(todo_id), str(parent_id)),
    )
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Parent todo cannot be a descendant")


def _validate_todo_references(cur, body, todo_id: UUID | None = None, fields: set[str] | None = None):
    fields = fields or set(body.__class__.model_fields.keys())

    if "subtree_id" in fields:
        if body.subtree_id is None:
            raise HTTPException(status_code=400, detail="Subtree is required")
        _ensure_exists(cur, "subtrees", str(body.subtree_id), "Subtree")
    if "project_id" in fields:
        _ensure_exists(cur, "projects", body.project_id, "Project")

    person_fields = ["proposer_id", "tracker_id"]
    for field in person_fields:
        if field in fields and hasattr(body, field):
            _ensure_people_exist(cur, [getattr(body, field)], LOG_FIELD_LABELS.get(field, field))

    people_array_fields = [
        "watcher_ids",
        "process_manager_ids",
        "technical_advisor_ids",
        "main_force_ids",
        "backup_force_ids",
    ]
    for field in people_array_fields:
        if field in fields and getattr(body, field, None) is not None:
            _ensure_people_exist(cur, getattr(body, field), LOG_FIELD_LABELS.get(field, field))

    if "parent_id" in fields:
        _ensure_parent_allowed(cur, todo_id, body.parent_id)

    if "depends_on_ids" in fields and getattr(body, "depends_on_ids", None) is not None:
        dep_ids = body.depends_on_ids
        if todo_id and any(str(dep_id) == str(todo_id) for dep_id in dep_ids):
            raise HTTPException(status_code=400, detail="Todo cannot depend on itself")
        _ensure_todos_exist(cur, dep_ids, "Depends-on todo")


# ── Health ────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    result = {"status": "ok", "db": True}
    try:
        query_one("SELECT 1")
    except Exception as exc:
        result["status"] = "degraded"
        result["db"] = False
        result["db_error"] = str(exc)
    return result


# ── Stats ─────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=StatsOut)
def get_stats():
    now = datetime.now(timezone.utc)
    today_start, tomorrow_start = _sync_day_bounds(now)
    next_7_days_end = tomorrow_start + timedelta(days=7)
    rows = query(f"""
        SELECT
            COUNT(*) FILTER (WHERE t.deleted_at IS NULL) AS total,
            COUNT(*) FILTER (WHERE t.is_bug = TRUE AND t.deleted_at IS NULL) AS bugs,
            COUNT(*) FILTER (WHERE t.status = 'pending' AND t.deleted_at IS NULL) AS pending,
            COUNT(*) FILTER (WHERE t.status = 'completed' AND t.deleted_at IS NULL) AS completed,
            COUNT(*) FILTER (WHERE t.status = 'cancelled' AND t.deleted_at IS NULL) AS cancelled,
            COUNT(*) FILTER (WHERE t.status = 'expired' AND t.deleted_at IS NULL) AS expired,
            COUNT(*) FILTER (WHERE t.priority = 'low' AND t.deleted_at IS NULL) AS low,
            COUNT(*) FILTER (WHERE t.priority = 'normal' AND t.deleted_at IS NULL) AS normal,
            COUNT(*) FILTER (WHERE t.priority = 'high' AND t.deleted_at IS NULL) AS high,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND progress.recorded_at >= %s
                  AND progress.recorded_at < %s
                  AND progress.confirmed_at IS NULL
            ) AS sync_filled_today,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND progress.confirmed_at IS NOT NULL
                  AND confirmed.last_confirmed_at >= %s
                  AND confirmed.last_confirmed_at < %s
            ) AS sync_synced_today,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND ({NEXT_SYNC_SQL}) < %s
            ) AS sync_overdue,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND ({NEXT_SYNC_SQL}) >= %s
                  AND ({NEXT_SYNC_SQL}) < %s
            ) AS sync_due_today,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND ({NEXT_SYNC_SQL}) < %s
            ) AS sync_needs_today,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND ({NEXT_SYNC_SQL}) >= %s
                  AND ({NEXT_SYNC_SQL}) < %s
            ) AS sync_next_7_days,
            COUNT(*) FILTER (
                WHERE t.status = 'pending' AND t.deleted_at IS NULL
                  AND (
                      t.track_frequency IS NULL OR
                      t.track_frequency NOT IN ('daily', 'every_3_days', 'weekly', 'biweekly', 'monthly')
                  )
            ) AS sync_not_configured
        {TODO_LIST_FROM}
    """, (
        today_start,
        tomorrow_start,
        today_start,
        tomorrow_start,
        today_start,
        today_start,
        tomorrow_start,
        tomorrow_start,
        tomorrow_start,
        next_7_days_end,
    ))
    r = rows[0]
    return StatsOut(**r)


# ── People ────────────────────────────────────────────────────────

@app.get("/api/people", response_model=list[PersonOut])
def list_people():
    return query("SELECT id, canonical_name FROM people ORDER BY id")


# ── Projects ──────────────────────────────────────────────────────

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects():
    return query("SELECT id, name FROM projects ORDER BY id")


# ── Subtrees ──────────────────────────────────────────────────────

@app.get("/api/subtrees", response_model=list[SubtreeOut])
def list_subtrees():
    rows = query("""
        SELECT s.*,
               (SELECT COUNT(*) FROM todos t
                WHERE t.subtree_id = s.id AND t.deleted_at IS NULL) AS todo_count
        FROM subtrees s
        ORDER BY s.level, s.name
    """)
    nodes: dict[UUID, SubtreeOut] = {}
    roots: list[SubtreeOut] = []
    for r in rows:
        node = SubtreeOut(
            id=r["id"],
            name=r["name"],
            parent_id=r["parent_id"],
            level=r["level"],
            description=r.get("description"),
            todo_count=r["todo_count"],
            children=[],
        )
        nodes[node.id] = node
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


# ── Todos CRUD ────────────────────────────────────────────────────

NEXT_SYNC_SQL = """
    CASE t.track_frequency
        WHEN 'daily' THEN COALESCE(confirmed.last_confirmed_at, t.created_at) + INTERVAL '1 day'
        WHEN 'every_3_days' THEN COALESCE(confirmed.last_confirmed_at, t.created_at) + INTERVAL '3 days'
        WHEN 'weekly' THEN COALESCE(confirmed.last_confirmed_at, t.created_at) + INTERVAL '7 days'
        WHEN 'biweekly' THEN COALESCE(confirmed.last_confirmed_at, t.created_at) + INTERVAL '14 days'
        WHEN 'monthly' THEN COALESCE(confirmed.last_confirmed_at, t.created_at) + INTERVAL '1 month'
        ELSE NULL
    END
"""

SYNC_STATUS_SQL = f"""
    CASE
        WHEN t.status <> 'pending' THEN 'closed'
        WHEN progress.recorded_at IS NOT NULL
          AND progress.confirmed_at IS NULL
          AND (progress.recorded_at AT TIME ZONE 'Asia/Shanghai')::date =
              (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
            THEN 'filled_today'
        WHEN progress.recorded_at IS NOT NULL
          AND progress.confirmed_at IS NULL
          AND (({NEXT_SYNC_SQL}) AT TIME ZONE 'Asia/Shanghai')::date <
              (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
            THEN 'pending_confirmation_overdue'
        WHEN progress.recorded_at IS NOT NULL AND progress.confirmed_at IS NULL
            THEN 'pending_confirmation'
        WHEN confirmed.last_confirmed_at IS NOT NULL
          AND (confirmed.last_confirmed_at AT TIME ZONE 'Asia/Shanghai')::date =
              (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
            THEN 'synced_today'
        WHEN t.track_frequency IS NULL
          OR t.track_frequency NOT IN ('daily', 'every_3_days', 'weekly', 'biweekly', 'monthly')
            THEN 'not_configured'
        WHEN (({NEXT_SYNC_SQL}) AT TIME ZONE 'Asia/Shanghai')::date <
             (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date THEN 'overdue'
        WHEN (({NEXT_SYNC_SQL}) AT TIME ZONE 'Asia/Shanghai')::date =
             (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date THEN 'due_today'
        ELSE 'scheduled'
    END
"""


def _sync_due_condition(
    sync_due: str,
    now: Optional[datetime] = None,
) -> tuple[str, tuple]:
    if sync_due not in SYNC_DUE_FILTERS:
        raise HTTPException(status_code=400, detail=f"Invalid sync due filter: {sync_due}")

    now = now or datetime.now(timezone.utc)
    today_start, tomorrow_start = _sync_day_bounds(now)
    next_sync = f"({NEXT_SYNC_SQL})"
    pending = "t.status = 'pending'"

    if sync_due == "needs_today":
        return f"{pending} AND {next_sync} < %s", (tomorrow_start,)
    if sync_due == "filled_today":
        return (
            f"{pending} AND progress.recorded_at >= %s AND progress.recorded_at < %s "
            "AND progress.confirmed_at IS NULL",
            (today_start, tomorrow_start),
        )
    if sync_due == "synced_today":
        return (
            f"{pending} AND progress.confirmed_at IS NOT NULL "
            "AND confirmed.last_confirmed_at >= %s AND confirmed.last_confirmed_at < %s",
            (today_start, tomorrow_start),
        )
    if sync_due == "overdue":
        return f"{pending} AND {next_sync} < %s", (today_start,)
    if sync_due == "due_today":
        return (
            f"{pending} AND {next_sync} >= %s AND {next_sync} < %s",
            (today_start, tomorrow_start),
        )
    if sync_due == "next_3_days":
        return (
            f"{pending} AND {next_sync} >= %s AND {next_sync} < %s",
            (tomorrow_start, tomorrow_start + timedelta(days=3)),
        )
    if sync_due == "next_7_days":
        return (
            f"{pending} AND {next_sync} >= %s AND {next_sync} < %s",
            (tomorrow_start, tomorrow_start + timedelta(days=7)),
        )
    return (
        f"""{pending} AND (
                t.track_frequency IS NULL OR
                t.track_frequency NOT IN ('daily', 'every_3_days', 'weekly', 'biweekly', 'monthly')
            )""",
        (),
    )

TODO_LIST_FROM = """
    FROM todos t
    JOIN subtrees s ON t.subtree_id = s.id
    LEFT JOIN projects p ON t.project_id = p.id
    LEFT JOIN people pp ON t.proposer_id = pp.id
    LEFT JOIN people tr ON t.tracker_id = tr.id
    LEFT JOIN todos pt ON t.parent_id = pt.id AND pt.deleted_at IS NULL
    LEFT JOIN LATERAL (
        SELECT h.id, h.content, h.recorded_at, h.confirmed_at, h.confirmed_by, h.source
        FROM todo_progress_history h
        WHERE h.todo_id = t.id
          AND h.revoked_at IS NULL
        ORDER BY h.recorded_at DESC,
                 (h.confirmed_at IS NULL) DESC,
                 h.id DESC
        LIMIT 1
    ) progress ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(h.confirmed_at) AS last_confirmed_at
        FROM todo_progress_history h
        WHERE h.todo_id = t.id
          AND h.confirmed_at IS NOT NULL
          AND h.revoked_at IS NULL
    ) confirmed ON TRUE
"""

TODO_LIST_SELECT = f"""
    SELECT t.*,
           s.name AS subtree_name,
           p.name AS project_name,
           pp.canonical_name AS proposer_name,
           tr.canonical_name AS tracker_name,
           pt.title AS parent_title,
           progress.id AS last_progress_id,
           progress.content AS last_progress_content,
           progress.recorded_at AS last_progress_at,
           progress.confirmed_at AS last_progress_confirmed_at,
           progress.source AS last_progress_source,
           confirmed.last_confirmed_at,
           COALESCE(ARRAY(
               SELECT person.canonical_name
               FROM UNNEST(t.main_force_ids) WITH ORDINALITY AS role(person_id, position)
               JOIN people person ON person.id = role.person_id
               ORDER BY role.position
           ), ARRAY[]::TEXT[]) AS main_force_names,
           COALESCE(ARRAY(
               SELECT person.canonical_name
               FROM UNNEST(t.process_manager_ids) WITH ORDINALITY AS role(person_id, position)
               JOIN people person ON person.id = role.person_id
               ORDER BY role.position
           ), ARRAY[]::TEXT[]) AS process_manager_names
    {TODO_LIST_FROM}
"""


@app.get("/api/todos", response_model=PaginatedResponse)
def list_todos(
    status: Optional[str] = Query(None),
    is_bug: Optional[bool] = Query(None),
    sync_status: Optional[str] = Query(None),
    sync_due: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    subtree_id: Optional[UUID] = Query(None),
    project_id: Optional[int] = Query(None),
    parent_id: Optional[UUID] = Query(None),
    main_force_id: Optional[int] = Query(None),
    process_manager_id: Optional[int] = Query(None),
    participant_id: Optional[int] = Query(None),
    parents_only: bool = Query(False),
    tree: bool = Query(False),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    sort: str = Query("created_at_desc"),
):
    conditions = ["t.deleted_at IS NULL"]
    params: list = []

    if status and status in TODO_STATUSES:
        conditions.append("t.status = %s")
        params.append(status)
    if is_bug is not None:
        conditions.append("t.is_bug = %s")
        params.append(is_bug)
    if sync_status:
        valid_sync_statuses = {
            "not_configured",
            "filled_today",
            "pending_confirmation",
            "pending_confirmation_overdue",
            "synced_today",
            "overdue",
            "due_today",
            "scheduled",
            "closed",
        }
        if sync_status not in valid_sync_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid sync status: {sync_status}")
        conditions.append(f"({SYNC_STATUS_SQL}) = %s")
        params.append(sync_status)
    if sync_due:
        sync_due_sql, sync_due_params = _sync_due_condition(sync_due)
        conditions.append(f"({sync_due_sql})")
        params.extend(sync_due_params)
    if priority:
        if priority not in TODO_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
        conditions.append("t.priority = %s")
        params.append(priority)
    if subtree_id:
        conditions.append("t.subtree_id = %s")
        params.append(str(subtree_id))
    if project_id:
        conditions.append("t.project_id = %s")
        params.append(project_id)
    if parent_id:
        conditions.append("t.parent_id = %s")
        params.append(str(parent_id))
    if main_force_id:
        conditions.append("%s = ANY(t.main_force_ids)")
        params.append(main_force_id)
    if process_manager_id:
        conditions.append("%s = ANY(t.process_manager_ids)")
        params.append(process_manager_id)
    if participant_id:
        conditions.append("(%s = ANY(t.main_force_ids) OR %s = ANY(t.process_manager_ids))")
        params.extend([participant_id, participant_id])
    if parents_only:
        conditions.append(
            """EXISTS (
                   SELECT 1 FROM todos child
                   WHERE child.parent_id = t.id
                     AND child.deleted_at IS NULL
               )"""
        )
    if q:
        conditions.append("t.title ILIKE %s")
        params.append(f"%{q}%")

    where = " AND ".join(conditions)

    sort_map = {
        "created_at_desc": "t.created_at DESC, t.id ASC",
        "created_at_asc": "t.created_at ASC, t.id ASC",
        "updated_at_desc": "t.updated_at DESC, t.id ASC",
        "updated_at_asc": "t.updated_at ASC, t.id ASC",
        "priority_desc": (
            "CASE t.priority "
            "WHEN 'high' THEN 3 WHEN 'normal' THEN 2 "
            "WHEN 'low' THEN 1 END DESC, "
            "t.created_at DESC, t.id ASC"
        ),
        "priority_asc": (
            "CASE t.priority "
            "WHEN 'high' THEN 3 WHEN 'normal' THEN 2 "
            "WHEN 'low' THEN 1 END ASC, "
            "t.created_at DESC, t.id ASC"
        ),
        "next_sync_asc": (
            f"({NEXT_SYNC_SQL}) ASC NULLS LAST, t.created_at DESC, t.id ASC"
        ),
        "next_sync_desc": (
            f"({NEXT_SYNC_SQL}) DESC NULLS LAST, t.created_at DESC, t.id ASC"
        ),
    }
    order_by = sort_map.get(sort, "t.created_at DESC, t.id ASC")

    if tree:
        tree_sql = f"""
            WITH RECURSIVE matched_ids(id, parent_id) AS (
                SELECT t.id, t.parent_id
                {TODO_LIST_FROM}
                WHERE {where}
            ),
            ancestor_ids(id, parent_id) AS (
                SELECT id, parent_id FROM matched_ids
                UNION
                SELECT parent.id, parent.parent_id
                FROM todos parent
                JOIN ancestor_ids child ON child.parent_id = parent.id
                WHERE parent.deleted_at IS NULL
            ),
            descendant_ids(id, parent_id) AS (
                SELECT id, parent_id FROM matched_ids
                UNION
                SELECT child.id, child.parent_id
                FROM todos child
                JOIN descendant_ids parent ON child.parent_id = parent.id
                WHERE child.deleted_at IS NULL
            ),
            tree_ids(id) AS (
                SELECT id FROM ancestor_ids
                UNION
                SELECT id FROM descendant_ids
            )
            {TODO_LIST_SELECT}
            WHERE t.id IN (SELECT id FROM tree_ids)
            ORDER BY {order_by}
        """
        rows = query(tree_sql, tuple(params))
        items = [_build_todo_list_item(row) for row in rows]
        return PaginatedResponse(
            items=items,
            total=len(items),
            page=1,
            size=len(items),
            pages=1 if items else 0,
        )

    count_sql = f"SELECT COUNT(*) AS cnt {TODO_LIST_FROM} WHERE {where}"
    total = query_one(count_sql, tuple(params))["cnt"]

    offset = (page - 1) * size
    params.append(size)
    params.append(offset)

    list_sql = (
        f"{TODO_LIST_SELECT} WHERE {where} ORDER BY {order_by} LIMIT %s OFFSET %s"
    )
    rows = query(list_sql, tuple(params))
    items = [_build_todo_list_item(r) for r in rows]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total > 0 else 0,
    )


@app.get("/api/todos/{todo_id}", response_model=TodoDetailOut)
def get_todo(todo_id: UUID):
    row = query_one(
        f"{TODO_LIST_SELECT} WHERE t.id = %s AND t.deleted_at IS NULL",
        (str(todo_id),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Todo not found")
    return _build_todo_detail(row)


@app.put("/api/todos/{todo_id}/child-weights", response_model=TodoDetailOut)
def update_child_weights(todo_id: UUID, body: ChildWeightsUpdate, request: Request):
    username = _require_username(request)
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            parent = _fetch_one(
                cur,
                """SELECT id, title
                   FROM todos
                   WHERE id = %s AND deleted_at IS NULL
                   FOR UPDATE""",
                (str(todo_id),),
            )
            if not parent:
                raise HTTPException(status_code=404, detail="Todo not found")

            cur.execute(
                """SELECT id, title, parent_weight_percent
                   FROM todos
                   WHERE parent_id = %s AND deleted_at IS NULL
                   ORDER BY created_at ASC, id ASC
                   FOR UPDATE""",
                (str(todo_id),),
            )
            children = cur.fetchall()
            if not children:
                raise HTTPException(status_code=400, detail="该 Todo 没有可设置占比的子 Todo")

            requested_ids = [str(item.todo_id) for item in body.items]
            if len(requested_ids) != len(set(requested_ids)):
                raise HTTPException(status_code=400, detail="子 Todo 占比列表中存在重复项")

            existing_by_id = {str(child["id"]): child for child in children}
            requested_by_id = {str(item.todo_id): item.percent for item in body.items}
            missing_ids = set(existing_by_id) - set(requested_by_id)
            unknown_ids = set(requested_by_id) - set(existing_by_id)
            if missing_ids or unknown_ids:
                raise HTTPException(
                    status_code=400,
                    detail="必须一次提交当前父 Todo 下的全部直属子 Todo 占比",
                )

            weight_total = sum(requested_by_id.values())
            if weight_total > 100:
                raise HTTPException(
                    status_code=400,
                    detail=f"子 Todo 占比合计不能超过 100%，当前为 {weight_total}%",
                )

            changed_children = []
            for child_id, percent in requested_by_id.items():
                child = existing_by_id[child_id]
                old_percent = child.get("parent_weight_percent") or 0
                if old_percent == percent:
                    continue
                cur.execute(
                    """UPDATE todos
                       SET parent_weight_percent = %s, updated_at = %s
                       WHERE id = %s""",
                    (percent, now, child_id),
                )
                changed_children.append(
                    {
                        "id": child_id,
                        "title": child["title"],
                        "old": old_percent,
                        "new": percent,
                    }
                )

            if changed_children:
                cur.execute(
                    "UPDATE todos SET updated_at = %s WHERE id = %s",
                    (now, str(todo_id)),
                )
                change_text = "；".join(
                    f"{item['title'][:60]}: {item['old']}% -> {item['new']}%"
                    for item in changed_children
                )
                _log(
                    username,
                    "weights_updated",
                    "todo",
                    str(todo_id),
                    (
                        f"调整子 Todo 占比；{change_text}；"
                        f"子项合计 {weight_total}%，父 Todo 自身 {100 - weight_total}%"
                    ),
                    changes={
                        "child_weights": {
                            "label": "子 Todo 占比",
                            "items": changed_children,
                        },
                        "weight_total": {
                            "label": "子项占比合计",
                            "new": weight_total,
                        },
                    },
                    cur=cur,
                )
                _roll_up_parent_work_status(cur, [todo_id], username, now=now)
                _roll_up_parent_sync_status(cur, [todo_id], username, now=now)

    return get_todo(todo_id)


@app.post("/api/todos", response_model=TodoDetailOut, status_code=201)
def create_todo(body: TodoCreate, request: Request):
    if body.priority not in TODO_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {body.priority}")
    track_frequency = _normalize_sync_frequency(body.track_frequency)
    progress_prompt = body.progress_prompt.strip()
    if not progress_prompt:
        raise HTTPException(status_code=400, detail="Progress prompt cannot be empty")

    username = _require_username(request)
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _validate_todo_references(cur, body)
            parent_weight_percent = (
                _remaining_parent_weight(cur, body.parent_id)
                if body.parent_id
                else None
            )
            cur.execute(
                """INSERT INTO todos (title, is_bug, description, priority, subtree_id, project_id,
                   proposer_id, parent_id, parent_weight_percent, depends_on_ids,
                   watcher_ids, process_manager_ids, technical_advisor_ids,
                   main_force_ids, backup_force_ids, track_frequency,
                   progress_prompt, zulip_stream, zulip_topic, image_paths)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (
                    body.title, body.is_bug, body.description, body.priority,
                    str(body.subtree_id), body.project_id,
                    body.proposer_id or 1,
                    str(body.parent_id) if body.parent_id else None,
                    parent_weight_percent,
                    [uuid.UUID(str(x)) for x in body.depends_on_ids],
                    body.watcher_ids, body.process_manager_ids,
                    body.technical_advisor_ids, body.main_force_ids,
                    body.backup_force_ids, track_frequency, progress_prompt,
                    body.zulip_stream, body.zulip_topic, body.image_paths,
                ),
            )
            new_id = cur.fetchone()["id"]
            _log(
                username,
                "created",
                "todo",
                str(new_id),
                f"创建 Todo；标题: {body.title[:200]}",
                changes={
                    "title": {
                        "label": LOG_FIELD_LABELS["title"],
                        "old": None,
                        "new": body.title,
                    },
                    "is_bug": {
                        "label": LOG_FIELD_LABELS["is_bug"],
                        "old": None,
                        "new": body.is_bug,
                    },
                },
                cur=cur,
            )
            if body.parent_id:
                _roll_up_parent_work_status(cur, [body.parent_id], username)
                _roll_up_parent_sync_status(cur, [body.parent_id], username)
    return get_todo(new_id)


@app.put("/api/todos/{todo_id}", response_model=TodoDetailOut)
def update_todo(todo_id: UUID, body: TodoUpdate, request: Request):
    existing = query_one(
        "SELECT * FROM todos WHERE id = %s AND deleted_at IS NULL",
        (str(todo_id),),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Todo not found")

    if body.status is not None and body.status not in TODO_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    if body.priority is not None and body.priority not in TODO_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {body.priority}")

    provided_fields = set(body.model_fields_set)
    if "title" in provided_fields and (body.title is None or not body.title.strip()):
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if "progress_prompt" in provided_fields and (
        body.progress_prompt is None or not body.progress_prompt.strip()
    ):
        raise HTTPException(status_code=400, detail="Progress prompt cannot be empty")

    track_frequency = (
        _normalize_sync_frequency(body.track_frequency)
        if "track_frequency" in provided_fields
        else body.track_frequency
    )

    updates: list[str] = []
    params: list = []

    field_values = {
        "title": body.title,
        "is_bug": body.is_bug,
        "description": body.description,
        "status": body.status,
        "priority": body.priority,
        "subtree_id": str(body.subtree_id) if body.subtree_id else None,
        "project_id": body.project_id,
        "tracker_id": body.tracker_id,
        "parent_id": str(body.parent_id) if body.parent_id else None,
        "depends_on_ids": [uuid.UUID(str(x)) for x in body.depends_on_ids] if body.depends_on_ids is not None else None,
        "watcher_ids": body.watcher_ids,
        "process_manager_ids": body.process_manager_ids,
        "technical_advisor_ids": body.technical_advisor_ids,
        "main_force_ids": body.main_force_ids,
        "backup_force_ids": body.backup_force_ids,
        "track_frequency": track_frequency,
        "progress_prompt": body.progress_prompt.strip() if body.progress_prompt else body.progress_prompt,
        "zulip_stream": body.zulip_stream,
        "zulip_topic": body.zulip_topic,
        "image_paths": body.image_paths,
        "completed_at": body.completed_at,
    }

    for col, val in field_values.items():
        if col in provided_fields:
            if col == "completed_at" and body.status == "completed" and val is None:
                continue
            updates.append(f"{col} = %s")
            params.append(val)

    requested_changes = {
        k: field_values[k]
        for k in provided_fields
        if k in field_values and not (k == "completed_at" and body.status == "completed" and field_values[k] is None)
    }
    auto_changes = {}
    username = _require_username(request)

    if body.status == "completed" and body.completed_at is None:
        completed_at = datetime.now(timezone.utc)
        updates.append("completed_at = %s")
        params.append(completed_at)
        auto_changes["completed_at"] = completed_at
    elif body.status is not None and body.status != "completed":
        updates.append("completed_at = NULL")
        auto_changes["completed_at"] = None

    if body.status is not None and body.status != existing["status"]:
        updates.append("auto_completed_by_children = FALSE")
        auto_changes["auto_completed_by_children"] = False

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = %s")
    params.append(datetime.now(timezone.utc))
    params.append(str(todo_id))

    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _validate_todo_references(cur, body, todo_id=todo_id, fields=provided_fields)
            parent_changed = (
                "parent_id" in provided_fields
                and str(field_values["parent_id"] or "")
                != str(existing.get("parent_id") or "")
            )
            if parent_changed:
                new_parent_weight = (
                    _remaining_parent_weight(cur, field_values["parent_id"])
                    if field_values["parent_id"]
                    else None
                )
                updates.insert(len(updates) - 1, "parent_weight_percent = %s")
                params.insert(len(params) - 2, new_parent_weight)
                auto_changes["parent_weight_percent"] = new_parent_weight
            if body.status == "completed":
                dep_ids = (
                    field_values["depends_on_ids"]
                    if "depends_on_ids" in provided_fields
                    else existing.get("depends_on_ids")
                )
                _ensure_dependencies_completed(cur, todo_id, dep_ids)
                _ensure_children_ended(cur, todo_id)
            sql = f"UPDATE todos SET {', '.join(updates)} WHERE id = %s"
            try:
                cur.execute(sql, tuple(params))
            except psycopg2.Error as exc:
                message = str(exc)
                if "unfinished predecessor" in message:
                    raise HTTPException(
                        status_code=400,
                        detail="无法完成 Todo：存在未完成的依赖项",
                    ) from exc
                raise
            detail = _build_change_detail(existing, requested_changes, auto_changes)
            changes = _build_change_payload(existing, requested_changes, auto_changes)
            _log(
                username,
                body.status if body.status and body.status != "pending" else "updated",
                "todo", str(todo_id),
                detail,
                changes=changes,
                cur=cur,
            )
            current_parent_id = (
                field_values["parent_id"]
                if "parent_id" in provided_fields
                else existing.get("parent_id")
            )
            affected_parent_ids = {
                str(parent_id)
                for parent_id in (existing.get("parent_id"), current_parent_id)
                if parent_id
            }
            work_rollup_ids = set(affected_parent_ids)
            if {"status", "depends_on_ids"} & provided_fields:
                work_rollup_ids.add(str(todo_id))
            if body.status is not None and body.status != existing["status"]:
                work_rollup_ids.update(_todo_ids_depending_on(cur, todo_id))
            if work_rollup_ids:
                _roll_up_parent_work_status(cur, work_rollup_ids, username)
            if affected_parent_ids:
                _roll_up_parent_sync_status(cur, affected_parent_ids, username)
    return get_todo(todo_id)


@app.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: UUID, request: Request):
    now = datetime.now(timezone.utc)
    username = _require_username(request)
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            existing = _fetch_one(
                cur,
                "SELECT id, title, parent_id FROM todos WHERE id = %s AND deleted_at IS NULL",
                (str(todo_id),),
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Todo not found")
            dependent_todo_ids = _todo_ids_depending_on(cur, todo_id)
            cur.execute(
                "UPDATE todos SET deleted_at = %s, updated_at = %s WHERE id = %s",
                (now, now, str(todo_id)),
            )
            _log(
                username,
                "deleted",
                "todo",
                str(todo_id),
                f"删除 Todo；标题: {existing['title'][:200]}",
                changes={
                    "deleted_at": {
                        "label": "删除时间",
                        "old": None,
                        "new": now.isoformat(),
                    },
                    "title": {
                        "label": LOG_FIELD_LABELS["title"],
                        "old": existing["title"],
                        "new": None,
                    },
                },
                cur=cur,
            )
            work_rollup_ids = set(dependent_todo_ids)
            if existing.get("parent_id"):
                work_rollup_ids.add(str(existing["parent_id"]))
            if work_rollup_ids:
                _roll_up_parent_work_status(cur, work_rollup_ids, username, now=now)
            if existing.get("parent_id"):
                _roll_up_parent_sync_status(cur, [existing["parent_id"]], username, now=now)


# ── Todo progress ────────────────────────────────────────────────

@app.get("/api/todos/{todo_id}/progress", response_model=PaginatedResponse)
def list_todo_progress(
    todo_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    if not query_one(
        "SELECT id FROM todos WHERE id = %s AND deleted_at IS NULL",
        (str(todo_id),),
    ):
        raise HTTPException(status_code=404, detail="Todo not found")

    total = query_one(
        "SELECT COUNT(*) AS cnt FROM todo_progress_history WHERE todo_id = %s",
        (str(todo_id),),
    )["cnt"]
    offset = (page - 1) * size
    rows = query(
        """SELECT h.id, h.todo_id, h.content, h.recorded_at, h.recorded_by,
                  p.canonical_name AS recorded_by_name,
                  h.confirmed_at, h.confirmed_by,
                  confirmer.canonical_name AS confirmed_by_name,
                  h.source, h.revoked_at
           FROM todo_progress_history h
           JOIN people p ON p.id = h.recorded_by
           LEFT JOIN people confirmer ON confirmer.id = h.confirmed_by
           WHERE h.todo_id = %s
           ORDER BY h.recorded_at DESC,
                    (h.confirmed_at IS NULL) DESC,
                    h.id DESC
           LIMIT %s OFFSET %s""",
        (str(todo_id), size, offset),
    )
    return PaginatedResponse(
        items=[ProgressEntryOut(**row) for row in rows],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total > 0 else 0,
    )


@app.post(
    "/api/todos/{todo_id}/progress",
    response_model=ProgressCreateResponse,
    status_code=201,
)
def create_todo_progress(todo_id: UUID, body: ProgressCreate, request: Request):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Progress content cannot be empty")

    username = _require_username(request)
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            todo = _fetch_one(
                cur,
                """SELECT id, title, status, parent_id, track_frequency, created_at
                   FROM todos WHERE id = %s AND deleted_at IS NULL""",
                (str(todo_id),),
            )
            if not todo:
                raise HTTPException(status_code=404, detail="Todo not found")
            person = _resolve_person(cur, username)
            cur.execute(
                """INSERT INTO todo_progress_history
                       (todo_id, content, recorded_at, recorded_by)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, todo_id, content, recorded_at, recorded_by,
                             confirmed_at, confirmed_by, source, revoked_at""",
                (str(todo_id), content, now, person["id"]),
            )
            progress = cur.fetchone()
            progress["recorded_by_name"] = person["canonical_name"]
            progress["confirmed_by_name"] = None
            cur.execute(
                """SELECT MAX(confirmed_at) AS last_confirmed_at
                   FROM todo_progress_history
                   WHERE todo_id = %s
                     AND confirmed_at IS NOT NULL
                     AND revoked_at IS NULL""",
                (str(todo_id),),
            )
            last_confirmed_at = cur.fetchone()["last_confirmed_at"]
            cur.execute(
                "UPDATE todos SET updated_at = %s WHERE id = %s",
                (now, str(todo_id)),
            )
            _log(
                username,
                "progress_filled",
                "todo",
                str(todo_id),
                f"填写 Todo 进展；标题: {todo['title'][:120]}；内容: {content[:300]}",
                changes={
                    "progress": {
                        "label": "同步进展",
                        "old": None,
                        "new": content,
                    }
                },
                cur=cur,
            )
            if todo.get("parent_id"):
                _roll_up_parent_sync_status(
                    cur, [todo["parent_id"]], username, actor=person, now=now
                )
    next_sync_at, status_meta = _build_sync_info(
        todo["status"],
        todo.get("track_frequency"),
        todo["created_at"],
        progress["recorded_at"],
        progress["confirmed_at"],
        last_confirmed_at,
        now=now,
    )
    return ProgressCreateResponse(
        **progress,
        next_sync_at=next_sync_at,
        sync_status=status_meta.code,
        status_meta=status_meta,
    )


@app.post(
    "/api/todos/{todo_id}/progress/{progress_id}/confirm",
    response_model=ProgressCreateResponse,
)
def confirm_todo_progress(
    todo_id: UUID,
    progress_id: UUID,
    request: Request,
):
    username = _require_username(request)
    now = datetime.now(timezone.utc)
    with transaction() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            todo = _fetch_one(
                cur,
                """SELECT id, title, status, parent_id, track_frequency, created_at
                   FROM todos WHERE id = %s AND deleted_at IS NULL""",
                (str(todo_id),),
            )
            if not todo:
                raise HTTPException(status_code=404, detail="Todo not found")
            if todo["status"] != "pending":
                raise HTTPException(status_code=409, detail="Only pending todos can be synced")

            progress = _fetch_one(
                cur,
                """SELECT id, todo_id, content, recorded_at, recorded_by,
                          confirmed_at, confirmed_by, source, revoked_at
                   FROM todo_progress_history
                   WHERE id = %s AND todo_id = %s
                     AND revoked_at IS NULL
                   FOR UPDATE""",
                (str(progress_id), str(todo_id)),
            )
            if not progress:
                raise HTTPException(status_code=404, detail="Progress entry not found")
            if progress["confirmed_at"] is not None:
                raise HTTPException(status_code=409, detail="Progress entry is already confirmed")

            person = _resolve_person(cur, username)
            cur.execute(
                """UPDATE todo_progress_history
                   SET confirmed_at = %s, confirmed_by = %s
                   WHERE id = %s
                   RETURNING id, todo_id, content, recorded_at, recorded_by,
                             confirmed_at, confirmed_by, source, revoked_at""",
                (now, person["id"], str(progress_id)),
            )
            progress = cur.fetchone()
            recorder = _fetch_one(
                cur,
                "SELECT canonical_name FROM people WHERE id = %s",
                (progress["recorded_by"],),
            )
            progress["recorded_by_name"] = recorder["canonical_name"]
            progress["confirmed_by_name"] = person["canonical_name"]
            cur.execute(
                "UPDATE todos SET updated_at = %s WHERE id = %s",
                (now, str(todo_id)),
            )
            _log(
                username,
                "progress_confirmed",
                "todo",
                str(todo_id),
                f"确认 Todo 同步；标题: {todo['title'][:120]}",
                changes={
                    "progress_confirmation": {
                        "label": "同步确认",
                        "old": None,
                        "new": now.isoformat(),
                    }
                },
                cur=cur,
            )
            if todo.get("parent_id"):
                _roll_up_parent_sync_status(
                    cur, [todo["parent_id"]], username, actor=person, now=now
                )

    next_sync_at, status_meta = _build_sync_info(
        todo["status"],
        todo.get("track_frequency"),
        todo["created_at"],
        progress["recorded_at"],
        progress["confirmed_at"],
        progress["confirmed_at"],
        now=now,
    )
    return ProgressCreateResponse(
        **progress,
        next_sync_at=next_sync_at,
        sync_status=status_meta.code,
        status_meta=status_meta,
    )


# ── Operation Logs ────────────────────────────────────────────────

@app.get("/api/logs", response_model=PaginatedResponse)
def list_logs(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    conditions = ["1=1"]
    params: list = []
    if username:
        conditions.append("username = %s")
        params.append(username)
    if action:
        conditions.append("action = %s")
        params.append(action)

    where = " AND ".join(conditions)
    total = query_one(
        f"SELECT COUNT(*) AS cnt FROM operation_logs WHERE {where}", tuple(params)
    )["cnt"]
    offset = (page - 1) * size
    params.extend([size, offset])
    rows = query(
        f"SELECT * FROM operation_logs WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(params),
    )
    items = [LogEntryOut(**r) for r in rows]
    return PaginatedResponse(
        items=items, total=total, page=page, size=size,
        pages=math.ceil(total / size) if total > 0 else 0,
    )


# ── Subtree todos ────────────────────────────────────────────────

@app.get("/api/subtrees/{subtree_id}/todos", response_model=PaginatedResponse)
def list_todos_by_subtree(
    subtree_id: UUID,
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
):
    return list_todos(
        status=status,
        sync_status=None,
        sync_due=None,
        priority=None,
        subtree_id=subtree_id,
        project_id=None,
        parent_id=None,
        main_force_id=None,
        parents_only=False,
        q=None,
        page=page,
        size=size,
        sort="created_at_desc",
    )
