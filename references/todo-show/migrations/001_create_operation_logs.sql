CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
    ON operation_logs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_operation_logs_username
    ON operation_logs (username);

CREATE INDEX IF NOT EXISTS idx_operation_logs_action
    ON operation_logs (action);

CREATE INDEX IF NOT EXISTS idx_operation_logs_target
    ON operation_logs (target_type, target_id);
