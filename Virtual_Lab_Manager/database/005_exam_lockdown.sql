-- =====================================================================================
-- Migration v1.2: exam lockdown (strict web exam mode + Safe Exam Browser) and mentor unlock.
-- Needed for databases created before this version (fresh installs get it from 001_schema.sql).
-- Run AFTER 004:  psql "$ADMIN_DATABASE_URL" -f database/005_exam_lockdown.sql
-- =====================================================================================
BEGIN;

ALTER TABLE practicals ADD COLUMN IF NOT EXISTS lockdown_mode text NOT NULL DEFAULT 'off';
ALTER TABLE practicals ADD COLUMN IF NOT EXISTS seb_config_key text;
ALTER TABLE practicals ADD COLUMN IF NOT EXISTS seb_config_url text;
ALTER TABLE practicals DROP CONSTRAINT IF EXISTS practicals_lockdown_mode_check;
ALTER TABLE practicals ADD CONSTRAINT practicals_lockdown_mode_check CHECK (lockdown_mode IN ('off', 'exam', 'seb'));

-- allow server-generated lock/unlock events in the proctoring timeline
ALTER TABLE proctoring_events DROP CONSTRAINT IF EXISTS proctoring_events_event_type_check;
ALTER TABLE proctoring_events ADD CONSTRAINT proctoring_events_event_type_check CHECK (event_type IN (
    'session_start', 'paste_blocked', 'copy_blocked', 'cut_blocked', 'drop_blocked', 'context_menu_blocked',
    'devtools_blocked', 'focus_lost', 'fullscreen_exit', 'large_insertion', 'exam_locked', 'exam_unlocked'));

-- ---------------------------------------------------------------- exam lockdown (one row per student per practical)
CREATE TABLE IF NOT EXISTS exam_attempts (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    practical_id      uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id        uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status            text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'locked', 'submitted')),
    active_session_id uuid,                    -- the only browser tab allowed to work; NULL after a mentor unlock
    last_session_id   uuid,
    lock_reason       text,
    violations        integer     NOT NULL DEFAULT 0,
    unlock_count      integer     NOT NULL DEFAULT 0,
    started_at        timestamptz NOT NULL DEFAULT now(),
    last_heartbeat_at timestamptz,
    locked_at         timestamptz,
    unlocked_at       timestamptz,
    unlocked_by       uuid        REFERENCES users (id) ON DELETE SET NULL,
    submitted_at      timestamptz,
    UNIQUE (practical_id, student_id)
);
CREATE INDEX IF NOT EXISTS exam_attempts_locked_idx ON exam_attempts (practical_id) WHERE status = 'locked';

-- demo: Lab 4 runs in strict exam mode (skip on real data)
UPDATE practicals SET lockdown_mode = 'exam' WHERE id = '96452ec1-9b97-57b6-8ccf-00ce1a5a84af';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlm_app') THEN
        GRANT SELECT, INSERT, UPDATE ON exam_attempts TO vlm_app;
    END IF;
END
$$;

COMMIT;
