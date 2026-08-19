ALTER TABLE todo_progress_history
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmed_by INTEGER REFERENCES people(id);

-- Existing progress entries represented completed syncs before confirmation was introduced.
UPDATE todo_progress_history
SET confirmed_at = recorded_at,
    confirmed_by = recorded_by
WHERE confirmed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_todo_progress_history_todo_id_confirmed_at
    ON todo_progress_history (todo_id, confirmed_at DESC)
    WHERE confirmed_at IS NOT NULL;
