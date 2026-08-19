ALTER TABLE todos
    ADD COLUMN IF NOT EXISTS parent_weight_percent SMALLINT;

WITH ranked_children AS (
    SELECT
        id,
        COUNT(*) OVER (PARTITION BY parent_id)::INTEGER AS sibling_count,
        ROW_NUMBER() OVER (
            PARTITION BY parent_id
            ORDER BY created_at ASC, id ASC
        )::INTEGER AS sibling_position
    FROM todos
    WHERE parent_id IS NOT NULL
      AND deleted_at IS NULL
)
UPDATE todos AS child
SET parent_weight_percent =
    (100 / ranked.sibling_count)
    + CASE
        WHEN ranked.sibling_position <= (100 % ranked.sibling_count) THEN 1
        ELSE 0
      END
FROM ranked_children AS ranked
WHERE child.id = ranked.id;

UPDATE todos
SET parent_weight_percent = 0
WHERE parent_id IS NOT NULL
  AND deleted_at IS NOT NULL
  AND parent_weight_percent IS NULL;

UPDATE todos
SET parent_weight_percent = NULL
WHERE parent_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'todos_parent_weight_percent_check'
    ) THEN
        ALTER TABLE todos
            ADD CONSTRAINT todos_parent_weight_percent_check
            CHECK (
                (parent_id IS NULL AND parent_weight_percent IS NULL)
                OR
                (
                    parent_id IS NOT NULL
                    AND parent_weight_percent BETWEEN 0 AND 100
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_todos_parent_weight_active
    ON todos (parent_id, parent_weight_percent)
    WHERE deleted_at IS NULL;
