BEGIN;

ALTER TABLE task_product_points
    ALTER COLUMN points TYPE INTEGER
    USING ROUND(points)::INTEGER;

COMMIT;
