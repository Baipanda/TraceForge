"""Project Admin API — mentor-managed project registry for TraceForge SOP."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from database import DATABASE_PATH, execute, execute_returning_id, query, query_one
from schemas import (
    HealthOut,
    MemberIn,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SopReportCreate,
    SopReportOut,
)

app = FastAPI(title="TraceForge Project Admin", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MENTORS = [
    name.strip()
    for name in os.getenv("PROJECT_ADMIN_MENTORS", "traceforge-admin").split(",")
    if name.strip()
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_mentor(x_mentor: str | None) -> str:
    name = (x_mentor or "").strip()
    if not name:
        raise HTTPException(401, "X-Mentor header required")
    if name not in MENTORS:
        raise HTTPException(403, f"unknown mentor: {name}")
    return name


def _parse_filters(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def _row_to_project(row: dict[str, Any], members: list[MemberOut] | None = None) -> ProjectOut:
    return ProjectOut(
        project_id=row["project_id"],
        display_name=row["display_name"],
        description=row.get("description") or "",
        status=row["status"],
        zulip_stream=row.get("zulip_stream") or "",
        zulip_stream_id=row.get("zulip_stream_id") or "",
        zulip_topic=row.get("zulip_topic") or "",
        notify_topic=row.get("notify_topic") or "",
        docs_root=row.get("docs_root") or "",
        prd_path=row.get("prd_path") or "",
        tech_path=row.get("tech_path") or "",
        gitea_owner=row.get("gitea_owner") or "",
        gitea_repo=row.get("gitea_repo") or "",
        default_branch=row.get("default_branch") or "main",
        path_filters=_parse_filters(row.get("path_filters")),
        subtree_code=row.get("subtree_code") or "",
        todo_show_project_id=row.get("todo_show_project_id") or "",
        window_days=int(row.get("window_days") or 7),
        start_at=row.get("start_at"),
        target_at=row.get("target_at"),
        created_by=row.get("created_by") or "",
        updated_by=row.get("updated_by") or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        members=members or [],
    )


def _load_members(project_id: str) -> list[MemberOut]:
    rows = query(
        """
        SELECT id, project_id, person_name, person_id, role, created_at
        FROM project_members
        WHERE project_id = ?
        ORDER BY role, person_name
        """,
        (project_id,),
    )
    return [MemberOut(**r) for r in rows]


def _get_project_or_404(project_id: str, *, include_archived: bool = True) -> ProjectOut:
    row = query_one("SELECT * FROM projects WHERE project_id = ?", (project_id,))
    if not row:
        raise HTTPException(404, f"project not found: {project_id}")
    if not include_archived and row["status"] == "archived":
        raise HTTPException(404, f"project not found: {project_id}")
    return _row_to_project(row, _load_members(project_id))


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    try:
        query_one("SELECT 1 AS ok")
        db_ok = "ok"
    except Exception as exc:  # noqa: BLE001
        db_ok = f"error: {exc}"
    return HealthOut(status="ok" if db_ok == "ok" else "degraded", database=db_ok)


@app.get("/api/mentors")
def list_mentors() -> dict[str, Any]:
    return {"mentors": MENTORS, "database": str(DATABASE_PATH)}


@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> list[ProjectOut]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    elif not include_archived:
        clauses.append("status != 'archived'")
    if q:
        clauses.append("(project_id LIKE ? OR display_name LIKE ? OR zulip_topic LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = query(f"SELECT * FROM projects {where} ORDER BY updated_at DESC", params)
    return [_row_to_project(r, _load_members(r["project_id"])) for r in rows]


@app.get("/api/projects/resolve", response_model=ProjectOut)
def resolve_project(
    stream: str = Query(default=""),
    topic: str = Query(default=""),
    project_id: str = Query(default=""),
) -> ProjectOut:
    """Read API for Agent / SOP: resolve by id or Zulip stream+topic."""
    if project_id.strip():
        return _get_project_or_404(project_id.strip(), include_archived=False)
    if stream.strip() and topic.strip():
        row = query_one(
            """
            SELECT * FROM projects
            WHERE status != 'archived'
              AND zulip_stream = ? AND zulip_topic = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (stream.strip(), topic.strip()),
        )
        if not row:
            raise HTTPException(404, "no project bound to this stream/topic")
        return _row_to_project(row, _load_members(row["project_id"]))
    raise HTTPException(400, "provide project_id or stream+topic")


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str) -> ProjectOut:
    return _get_project_or_404(project_id)


@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, x_mentor: str | None = Header(default=None)) -> ProjectOut:
    mentor = _require_mentor(x_mentor)
    existing = query_one("SELECT project_id FROM projects WHERE project_id = ?", (body.project_id,))
    if existing:
        raise HTTPException(409, f"project_id already exists: {body.project_id}")
    now = _now()
    execute(
        """
        INSERT INTO projects (
            project_id, display_name, description, status,
            zulip_stream, zulip_stream_id, zulip_topic, notify_topic,
            docs_root, prd_path, tech_path,
            gitea_owner, gitea_repo, default_branch, path_filters,
            subtree_code, todo_show_project_id,
            window_days, start_at, target_at,
            created_by, updated_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.project_id,
            body.display_name,
            body.description,
            body.status,
            body.zulip_stream,
            body.zulip_stream_id,
            body.zulip_topic,
            body.notify_topic,
            body.docs_root,
            body.prd_path,
            body.tech_path,
            body.gitea_owner,
            body.gitea_repo,
            body.default_branch,
            json.dumps(body.path_filters, ensure_ascii=False),
            body.subtree_code,
            body.todo_show_project_id,
            body.window_days,
            body.start_at,
            body.target_at,
            mentor,
            mentor,
            now,
            now,
        ),
    )
    return _get_project_or_404(body.project_id)


@app.put("/api/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    x_mentor: str | None = Header(default=None),
) -> ProjectOut:
    mentor = _require_mentor(x_mentor)
    _get_project_or_404(project_id)
    now = _now()
    execute(
        """
        UPDATE projects SET
            display_name=?, description=?, status=?,
            zulip_stream=?, zulip_stream_id=?, zulip_topic=?, notify_topic=?,
            docs_root=?, prd_path=?, tech_path=?,
            gitea_owner=?, gitea_repo=?, default_branch=?, path_filters=?,
            subtree_code=?, todo_show_project_id=?,
            window_days=?, start_at=?, target_at=?,
            updated_by=?, updated_at=?
        WHERE project_id=?
        """,
        (
            body.display_name,
            body.description,
            body.status,
            body.zulip_stream,
            body.zulip_stream_id,
            body.zulip_topic,
            body.notify_topic,
            body.docs_root,
            body.prd_path,
            body.tech_path,
            body.gitea_owner,
            body.gitea_repo,
            body.default_branch,
            json.dumps(body.path_filters, ensure_ascii=False),
            body.subtree_code,
            body.todo_show_project_id,
            body.window_days,
            body.start_at,
            body.target_at,
            mentor,
            now,
            project_id,
        ),
    )
    return _get_project_or_404(project_id)


@app.delete("/api/projects/{project_id}", response_model=ProjectOut)
def archive_project(project_id: str, x_mentor: str | None = Header(default=None)) -> ProjectOut:
    mentor = _require_mentor(x_mentor)
    _get_project_or_404(project_id)
    execute(
        "UPDATE projects SET status='archived', updated_by=?, updated_at=? WHERE project_id=?",
        (mentor, _now(), project_id),
    )
    return _get_project_or_404(project_id)


@app.post("/api/projects/{project_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    project_id: str,
    body: MemberIn,
    x_mentor: str | None = Header(default=None),
) -> MemberOut:
    _require_mentor(x_mentor)
    _get_project_or_404(project_id)
    now = _now()
    try:
        mid = execute_returning_id(
            """
            INSERT INTO project_members (project_id, person_name, person_id, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, body.person_name.strip(), body.person_id.strip(), body.role, now),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(409, f"member conflict: {exc}") from exc
    row = query_one("SELECT * FROM project_members WHERE id = ?", (mid,))
    assert row
    return MemberOut(**row)


@app.delete("/api/projects/{project_id}/members/{member_id}")
def remove_member(
    project_id: str,
    member_id: int,
    x_mentor: str | None = Header(default=None),
) -> Response:
    _require_mentor(x_mentor)
    row = query_one(
        "SELECT id FROM project_members WHERE id = ? AND project_id = ?",
        (member_id, project_id),
    )
    if not row:
        raise HTTPException(404, "member not found")
    execute("DELETE FROM project_members WHERE id = ?", (member_id,))
    return Response(status_code=204)


def _report_out(row: dict[str, Any]) -> SopReportOut:
    meta: dict[str, Any]
    try:
        meta = json.loads(row.get("meta_json") or "{}")
        if not isinstance(meta, dict):
            meta = {}
    except json.JSONDecodeError:
        meta = {}
    return SopReportOut(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        pipeline=row["pipeline"],
        markdown_body=row["markdown_body"],
        meta_json=meta,
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


@app.get("/api/projects/{project_id}/reports", response_model=list[SopReportOut])
def list_reports(project_id: str) -> list[SopReportOut]:
    _get_project_or_404(project_id)
    rows = query(
        """
        SELECT * FROM sop_reports
        WHERE project_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    )
    return [_report_out(r) for r in rows]


@app.get("/api/reports/{report_id}", response_model=SopReportOut)
def get_report(report_id: int) -> SopReportOut:
    row = query_one("SELECT * FROM sop_reports WHERE id = ?", (report_id,))
    if not row:
        raise HTTPException(404, "report not found")
    return _report_out(row)


@app.post("/api/reports", response_model=SopReportOut, status_code=201)
def create_report(body: SopReportCreate) -> SopReportOut:
    """Used later by TraceForge progress SOP to publish markdown results."""
    _get_project_or_404(body.project_id, include_archived=False)
    rid = execute_returning_id(
        """
        INSERT INTO sop_reports (project_id, title, pipeline, markdown_body, meta_json, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.project_id,
            body.title,
            body.pipeline,
            body.markdown_body,
            json.dumps(body.meta_json, ensure_ascii=False),
            body.created_by,
            _now(),
        ),
    )
    row = query_one("SELECT * FROM sop_reports WHERE id = ?", (rid,))
    assert row
    return _report_out(row)
