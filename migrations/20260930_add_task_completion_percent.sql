BEGIN;

ALTER TABLE task_executions
    ADD COLUMN IF NOT EXISTS completion_percent INTEGER;

ALTER TABLE task_executions
    DROP CONSTRAINT IF EXISTS ck_task_execution_completion_percent;

ALTER TABLE task_executions
    ADD CONSTRAINT ck_task_execution_completion_percent
    CHECK (completion_percent IS NULL OR completion_percent BETWEEN 0 AND 100);

COMMIT;
