CREATE TABLE IF NOT EXISTS project_members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    person_name  TEXT NOT NULL,
    person_id    TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'dev'
                 CHECK (role IN ('owner', 'pm', 'dev', 'reviewer', 'mentor')),
    created_at   TEXT NOT NULL,
    UNIQUE (project_id, person_name, role)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project
    ON project_members(project_id);
