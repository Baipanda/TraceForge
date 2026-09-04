from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProjectStatus = Literal["active", "paused", "done", "archived"]
MemberRole = Literal["owner", "pm", "dev", "reviewer", "mentor"]


class ProjectBase(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: ProjectStatus = "active"

    zulip_stream: str = ""
    zulip_stream_id: str = ""
    zulip_topic: str = ""
    notify_topic: str = ""

    docs_root: str = ""
    prd_path: str = ""
    tech_path: str = ""

    gitea_owner: str = ""
    gitea_repo: str = ""
    default_branch: str = "main"
    path_filters: list[str] = Field(default_factory=list)

    subtree_code: str = ""
    todo_show_project_id: str = ""

    window_days: int = Field(default=7, ge=1, le=365)
    start_at: str | None = None
    target_at: str | None = None


class ProjectCreate(ProjectBase):
    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")


class ProjectUpdate(ProjectBase):
    pass


class MemberIn(BaseModel):
    person_name: str = Field(min_length=1, max_length=120)
    person_id: str = ""
    role: MemberRole = "dev"


class MemberOut(MemberIn):
    id: int
    project_id: str
    created_at: str


class ProjectOut(ProjectBase):
    project_id: str
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str
    members: list[MemberOut] = Field(default_factory=list)


class SopReportCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    pipeline: str = "progress-sop-v1"
    markdown_body: str = Field(min_length=1)
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "system"


class SopReportOut(BaseModel):
    id: int
    project_id: str
    title: str
    pipeline: str
    markdown_body: str
    meta_json: dict[str, Any]
    created_by: str
    created_at: str


class HealthOut(BaseModel):
    status: str
    database: str
