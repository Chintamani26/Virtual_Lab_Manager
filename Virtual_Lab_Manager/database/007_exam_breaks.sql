-- =====================================================================================
-- Migration v1.4: Pause button. Declared exam breaks (MAX_BREAKS per exam, each up to BREAK_LIMIT;
-- see backend/app/services/exam.py). A break that runs over the limit locks the exam.
-- Needed for databases created before this version (fresh installs get it from 001_schema.sql).
-- Run AFTER 006:  psql "$ADMIN_DATABASE_URL" -f database/007_exam_breaks.sql
-- =====================================================================================
BEGIN;

ALTER TABLE exam_attempts ADD COLUMN IF NOT EXISTS paused_at timestamptz;
ALTER TABLE exam_attempts ADD COLUMN IF NOT EXISTS breaks_used integer NOT NULL DEFAULT 0;
ALTER TABLE exam_attempts ADD COLUMN IF NOT EXISTS break_ms bigint NOT NULL DEFAULT 0;

ALTER TABLE exam_attempts DROP CONSTRAINT IF EXISTS exam_attempts_status_check;
ALTER TABLE exam_attempts ADD CONSTRAINT exam_attempts_status_check
    CHECK (status IN ('active', 'paused', 'locked', 'submitted'));

COMMIT;
