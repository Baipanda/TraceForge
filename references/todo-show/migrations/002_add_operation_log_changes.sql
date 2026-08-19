ALTER TABLE operation_logs
    ADD COLUMN IF NOT EXISTS changes JSONB;

CREATE INDEX IF NOT EXISTS idx_operation_logs_changes
    ON operation_logs USING GIN (changes);
