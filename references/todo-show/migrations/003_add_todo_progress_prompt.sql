ALTER TABLE todos
    ADD COLUMN IF NOT EXISTS progress_prompt TEXT;

UPDATE todos
SET progress_prompt = '请说明本次完成了什么、当前问题或风险，以及下一步计划和预计时间。'
WHERE progress_prompt IS NULL OR BTRIM(progress_prompt) = '';

ALTER TABLE todos
    ALTER COLUMN progress_prompt SET DEFAULT '请说明本次完成了什么、当前问题或风险，以及下一步计划和预计时间。',
    ALTER COLUMN progress_prompt SET NOT NULL;

UPDATE todos
SET track_frequency = NULL
WHERE track_frequency IS NOT NULL AND BTRIM(track_frequency) = '';

UPDATE todos
SET track_frequency = 'weekly'
WHERE track_frequency IN ('每周', '每周同步');

CREATE TABLE IF NOT EXISTS todo_progress_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    todo_id UUID NOT NULL REFERENCES todos(id),
    content TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recorded_by INTEGER NOT NULL REFERENCES people(id)
);

CREATE INDEX IF NOT EXISTS idx_todo_progress_history_todo_id_recorded_at
    ON todo_progress_history (todo_id, recorded_at DESC);
