ALTER TABLE todos
    ADD COLUMN IF NOT EXISTS is_bug BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_todos_is_bug_active
    ON todos (is_bug)
    WHERE deleted_at IS NULL;
