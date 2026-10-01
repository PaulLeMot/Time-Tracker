BEGIN;

CREATE TABLE IF NOT EXISTS task_product_points (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    product_type_id INTEGER NOT NULL REFERENCES product_types(id) ON DELETE CASCADE,
    points INTEGER NOT NULL CHECK (points >= 0),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_task_product_points UNIQUE (task_id, product_type_id)
);

CREATE INDEX IF NOT EXISTS ix_task_product_points_task_id
    ON task_product_points(task_id);
CREATE INDEX IF NOT EXISTS ix_task_product_points_product_type_id
    ON task_product_points(product_type_id);

COMMIT;
