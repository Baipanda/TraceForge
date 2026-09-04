-- Progress SOP (and future pipelines) write markdown reports here for mentor UI.

CREATE TABLE IF NOT EXISTS sop_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    pipeline      TEXT NOT NULL DEFAULT 'progress-sop-v1',
    markdown_body TEXT NOT NULL,
    meta_json     TEXT NOT NULL DEFAULT '{}',
    created_by    TEXT NOT NULL DEFAULT 'system',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sop_reports_project_created
    ON sop_reports(project_id, created_at DESC);
