BEGIN;

CREATE TABLE IF NOT EXISTS independent_tasks (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    title VARCHAR(200),
    description TEXT,
    due_at TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_by_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_independent_tasks_task_id
    ON independent_tasks(task_id);
CREATE INDEX IF NOT EXISTS ix_independent_tasks_status
    ON independent_tasks(status);
CREATE INDEX IF NOT EXISTS ix_independent_tasks_created_by_id
    ON independent_tasks(created_by_id);

ALTER TABLE independent_tasks
    ADD COLUMN IF NOT EXISTS completion_data JSONB;

CREATE TABLE IF NOT EXISTS independent_task_assignees (
    independent_task_id INTEGER NOT NULL
        REFERENCES independent_tasks(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL
        REFERENCES employees(id) ON DELETE RESTRICT,
    notification_id INTEGER NOT NULL UNIQUE
        REFERENCES notifications(id) ON DELETE CASCADE,
    is_main BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (independent_task_id, employee_id)
);

CREATE INDEX IF NOT EXISTS ix_independent_task_assignees_employee_id
    ON independent_task_assignees(employee_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_independent_task_main_assignee
    ON independent_task_assignees(independent_task_id)
    WHERE is_main;

COMMIT;
