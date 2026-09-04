-- TraceForge project registry (mentor-managed). Soft-delete via status=archived.

CREATE TABLE IF NOT EXISTS projects (
    project_id       TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'paused', 'done', 'archived')),

    -- Zulip binding
    zulip_stream     TEXT NOT NULL DEFAULT '',
    zulip_stream_id  TEXT NOT NULL DEFAULT '',
    zulip_topic      TEXT NOT NULL DEFAULT '',
    notify_topic     TEXT NOT NULL DEFAULT '',

    -- Shared docs
    docs_root        TEXT NOT NULL DEFAULT '',
    prd_path         TEXT NOT NULL DEFAULT '',
    tech_path        TEXT NOT NULL DEFAULT '',

    -- Gitea
    gitea_owner      TEXT NOT NULL DEFAULT '',
    gitea_repo       TEXT NOT NULL DEFAULT '',
    default_branch   TEXT NOT NULL DEFAULT 'main',
    path_filters     TEXT NOT NULL DEFAULT '[]',  -- JSON array of path prefixes

    -- Todo / org alignment (todo-show or TraceForge subtree)
    subtree_code           TEXT NOT NULL DEFAULT '',
    todo_show_project_id   TEXT NOT NULL DEFAULT '',

    -- Timing
    window_days      INTEGER NOT NULL DEFAULT 7,
    start_at         TEXT,
    target_at        TEXT,

    -- Audit
    created_by       TEXT NOT NULL DEFAULT '',
    updated_by       TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_zulip
    ON projects(zulip_stream, zulip_topic);
CREATE INDEX IF NOT EXISTS idx_projects_gitea
    ON projects(gitea_owner, gitea_repo);
