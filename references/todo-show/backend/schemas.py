"""Pydantic schemas for request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt


# ── Enums ──────────────────────────────────────────────
TODO_STATUSES = ["pending", "completed", "cancelled", "expired"]
TODO_PRIORITIES = ["low", "normal", "high"]
TODO_SYNC_FREQUENCIES = ["daily", "every_3_days", "weekly", "biweekly", "monthly"]
DEFAULT_PROGRESS_PROMPT = "请说明本次完成了什么、当前问题或风险，以及下一步计划和预计时间。"


# ── People ─────────────────────────────────────────────
class PersonOut(BaseModel):
    id: int
    canonical_name: str


# ── Projects ───────────────────────────────────────────
class ProjectOut(BaseModel):
    id: int
    name: str


# ── Subtrees ───────────────────────────────────────────
class SubtreeOut(BaseModel):
    id: UUID
    name: str
    parent_id: Optional[UUID] = None
    level: int
    description: Optional[str] = None
    todo_count: int = 0
    children: list[SubtreeOut] = Field(default_factory=list)


# ── Todos ──────────────────────────────────────────────
class SyncStatusOut(BaseModel):
    code: str
    label: str
    hint: str
    tone: str


class TodoListOut(BaseModel):
    id: UUID
    title: str
    is_bug: bool = False
    status: str
    priority: str
    main_force_names: list[str] = Field(default_factory=list)
    process_manager_names: list[str] = Field(default_factory=list)
    subtree_name: str = ""
    project_name: Optional[str] = None
    parent_id: Optional[UUID] = None
    parent_title: Optional[str] = None
    auto_completed_by_children: bool = False
    track_frequency: Optional[str] = None
    track_frequency_label: Optional[str] = None
    progress_prompt: str = DEFAULT_PROGRESS_PROMPT
    last_progress_id: Optional[UUID] = None
    last_progress_at: Optional[datetime] = None
    last_progress_confirmed_at: Optional[datetime] = None
    last_progress_source: str = "manual"
    last_confirmed_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    sync_status: str
    status_meta: SyncStatusOut
    created_at: datetime
    updated_at: datetime


class TodoDetailOut(BaseModel):
    id: UUID
    title: str
    is_bug: bool = False
    description: Optional[str] = None
    status: str
    priority: str
    proposer_id: int
    proposer_name: str = ""
    tracker_id: Optional[int] = None
    tracker_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    subtree_id: UUID
    subtree_name: str = ""
    zulip_stream: Optional[str] = None
    zulip_topic: Optional[str] = None
    source_message_id: Optional[int] = None
    completed_at: Optional[datetime] = None
    auto_completed_by_children: bool = False
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    track_frequency: Optional[str] = None
    track_frequency_label: Optional[str] = None
    progress_prompt: str = DEFAULT_PROGRESS_PROMPT
    last_progress_content: Optional[str] = None
    last_progress_id: Optional[UUID] = None
    last_progress_at: Optional[datetime] = None
    last_progress_confirmed_at: Optional[datetime] = None
    last_progress_source: str = "manual"
    last_confirmed_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    sync_status: str
    status_meta: SyncStatusOut
    depends_on_ids: list[UUID] = Field(default_factory=list)
    depends_on_details: list[dict] = Field(default_factory=list)
    parent_id: Optional[UUID] = None
    parent_title: Optional[str] = None
    parent_weight_percent: Optional[int] = None
    children: list[dict] = Field(default_factory=list)
    watcher_ids: list[int] = Field(default_factory=list)
    watcher_names: list[str] = Field(default_factory=list)
    process_manager_ids: list[int] = Field(default_factory=list)
    process_manager_names: list[str] = Field(default_factory=list)
    technical_advisor_ids: list[int] = Field(default_factory=list)
    technical_advisor_names: list[str] = Field(default_factory=list)
    main_force_ids: list[int] = Field(default_factory=list)
    main_force_names: list[str] = Field(default_factory=list)
    backup_force_ids: list[int] = Field(default_factory=list)
    backup_force_names: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=2000)
    is_bug: bool = False
    description: Optional[str] = None
    priority: str = "normal"
    subtree_id: UUID
    project_id: Optional[int] = None
    proposer_id: Optional[int] = None
    parent_id: Optional[UUID] = None
    depends_on_ids: list[UUID] = Field(default_factory=list)
    watcher_ids: list[int] = Field(default_factory=list)
    process_manager_ids: list[int] = Field(default_factory=list)
    technical_advisor_ids: list[int] = Field(default_factory=list)
    main_force_ids: list[int] = Field(default_factory=list)
    backup_force_ids: list[int] = Field(default_factory=list)
    track_frequency: Optional[str] = None
    progress_prompt: str = Field(default=DEFAULT_PROGRESS_PROMPT, min_length=1, max_length=2000)
    zulip_stream: Optional[str] = None
    zulip_topic: Optional[str] = None
    image_paths: list[str] = Field(default_factory=list)


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    is_bug: Optional[bool] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    subtree_id: Optional[UUID] = None
    project_id: Optional[int] = None
    tracker_id: Optional[int] = None
    parent_id: Optional[UUID] = None
    depends_on_ids: Optional[list[UUID]] = None
    watcher_ids: Optional[list[int]] = None
    process_manager_ids: Optional[list[int]] = None
    technical_advisor_ids: Optional[list[int]] = None
    main_force_ids: Optional[list[int]] = None
    backup_force_ids: Optional[list[int]] = None
    track_frequency: Optional[str] = None
    progress_prompt: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    zulip_stream: Optional[str] = None
    zulip_topic: Optional[str] = None
    image_paths: Optional[list[str]] = None
    completed_at: Optional[datetime] = None


class ChildWeightItem(BaseModel):
    todo_id: UUID
    percent: StrictInt = Field(..., ge=0, le=100)


class ChildWeightsUpdate(BaseModel):
    items: list[ChildWeightItem]


class ProgressCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class ProgressEntryOut(BaseModel):
    id: UUID
    todo_id: UUID
    content: str
    recorded_at: datetime
    recorded_by: int
    recorded_by_name: str
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[int] = None
    confirmed_by_name: Optional[str] = None
    source: str = "manual"
    revoked_at: Optional[datetime] = None


class ProgressCreateResponse(ProgressEntryOut):
    next_sync_at: Optional[datetime] = None
    sync_status: str
    status_meta: SyncStatusOut


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int


class StatsOut(BaseModel):
    total: int
    bugs: int
    pending: int
    completed: int
    cancelled: int
    expired: int
    low: int
    normal: int
    high: int
    sync_needs_today: int
    sync_filled_today: int
    sync_synced_today: int
    sync_overdue: int
    sync_due_today: int
    sync_next_7_days: int
    sync_not_configured: int


# ── Logs ────────────────────────────────────────────────
class LogEntryOut(BaseModel):
    id: int
    username: str
    action: str
    target_type: str
    target_id: Optional[str] = None
    detail: Optional[str] = None
    changes: Optional[dict] = None
    created_at: datetime
