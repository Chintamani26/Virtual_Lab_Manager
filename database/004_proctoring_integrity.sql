-- =====================================================================================
-- Migration v1.1: proctored labs + academic-integrity reports.
-- Only needed for databases created with the ORIGINAL 001_schema.sql (fresh installs already include this).
-- Run as the schema owner:  psql "$ADMIN_DATABASE_URL" -f database/004_proctoring_integrity.sql
-- =====================================================================================
BEGIN;

ALTER TABLE practicals  ADD COLUMN IF NOT EXISTS proctored boolean NOT NULL DEFAULT true;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS integrity jsonb;

-- ---------------------------------------------------------------- proctoring & academic integrity
-- One row per proctored editor session (client-generated uuid per page load). baseline_files is captured
-- SERVER-SIDE at session start so "code that appeared without being typed" can be measured.
CREATE TABLE IF NOT EXISTS proctoring_sessions (
    id             uuid        PRIMARY KEY,
    practical_id   uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id     uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    baseline_files jsonb       NOT NULL DEFAULT '{}'::jsonb,
    stats          jsonb       NOT NULL DEFAULT '{}'::jsonb,   -- latest cumulative typing stats
    started_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proctoring_sessions_practical_student_idx ON proctoring_sessions (practical_id, student_id);

CREATE TABLE IF NOT EXISTS proctoring_events (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   uuid        NOT NULL REFERENCES proctoring_sessions (id) ON DELETE CASCADE,
    practical_id uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id   uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    event_type   text        NOT NULL CHECK (event_type IN (
                     'session_start', 'paste_blocked', 'copy_blocked', 'cut_blocked', 'drop_blocked',
                     'context_menu_blocked', 'devtools_blocked', 'focus_lost', 'fullscreen_exit', 'large_insertion')),
    detail       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    occurred_at  timestamptz NOT NULL,                 -- client clock (clamped server-side)
    created_at   timestamptz NOT NULL DEFAULT now()    -- server clock
);
CREATE INDEX IF NOT EXISTS proctoring_events_practical_student_idx
    ON proctoring_events (practical_id, student_id, occurred_at);

-- least-privilege app role (skip if you don't use database/003_app_role.sql)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlm_app') THEN
        GRANT SELECT, INSERT, UPDATE ON proctoring_sessions TO vlm_app;
        GRANT SELECT, INSERT ON proctoring_events TO vlm_app;
    END IF;
END
$$;

COMMIT;
