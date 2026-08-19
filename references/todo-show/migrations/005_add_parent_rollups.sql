ALTER TABLE todos
    ADD COLUMN IF NOT EXISTS auto_completed_by_children BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE todo_progress_history
    ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'todo_progress_history_source_check'
    ) THEN
        ALTER TABLE todo_progress_history
            ADD CONSTRAINT todo_progress_history_source_check
            CHECK (source IN ('manual', 'children_rollup'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_todos_parent_status_active
    ON todos (parent_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_todo_progress_active_confirmed
    ON todo_progress_history (todo_id, confirmed_at DESC)
    WHERE revoked_at IS NULL AND confirmed_at IS NOT NULL;
