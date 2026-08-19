WITH migrated AS (
    UPDATE todos
    SET priority = 'high',
        updated_at = NOW()
    WHERE priority = 'urgent'
    RETURNING id, title
)
INSERT INTO operation_logs (
    username,
    action,
    target_type,
    target_id,
    detail,
    changes
)
SELECT
    'system',
    'updated',
    'todo',
    id::TEXT,
    '移除紧急优先级，系统自动调整为高；标题: ' || LEFT(title, 200),
    jsonb_build_object(
        'priority',
        jsonb_build_object(
            'label', '优先级',
            'old', 'urgent',
            'new', 'high'
        )
    )
FROM migrated;
