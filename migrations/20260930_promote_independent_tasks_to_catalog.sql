BEGIN;

INSERT INTO tasks (name, task_type_id)
SELECT source.title, source.task_type_id
FROM (
    SELECT DISTINCT ON (LOWER(BTRIM(independent_tasks.title)))
        BTRIM(independent_tasks.title) AS title,
        tasks.task_type_id
    FROM independent_tasks
    JOIN tasks ON tasks.id = independent_tasks.task_id
    WHERE independent_tasks.title IS NOT NULL
      AND BTRIM(independent_tasks.title) <> ''
    ORDER BY LOWER(BTRIM(independent_tasks.title)), independent_tasks.id
) AS source
WHERE NOT EXISTS (
    SELECT 1 FROM tasks existing
    WHERE LOWER(existing.name) = LOWER(source.title)
);

UPDATE independent_tasks AS current_task
SET task_id = (
        SELECT tasks.id
        FROM tasks
        WHERE LOWER(tasks.name) = LOWER(BTRIM(current_task.title))
        ORDER BY tasks.id
        LIMIT 1
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE current_task.title IS NOT NULL
  AND BTRIM(current_task.title) <> ''
  AND current_task.task_id <> (
      SELECT tasks.id
      FROM tasks
      WHERE LOWER(tasks.name) = LOWER(BTRIM(current_task.title))
      ORDER BY tasks.id
      LIMIT 1
  );

UPDATE notifications
SET extra_data = jsonb_set(
    jsonb_set(notifications.extra_data::jsonb, '{task_id}', to_jsonb(independent_tasks.task_id)),
    '{task_name}',
    to_jsonb(COALESCE(independent_tasks.title, tasks.name))
)::json
FROM independent_task_assignees
JOIN independent_tasks
  ON independent_tasks.id = independent_task_assignees.independent_task_id
JOIN tasks ON tasks.id = independent_tasks.task_id
WHERE independent_task_assignees.notification_id = notifications.id;

COMMIT;
