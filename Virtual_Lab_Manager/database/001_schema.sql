-- =====================================================================================
-- Virtual Lab Manager — PostgreSQL schema (AlloyDB / Cloud SQL / Supabase compatible)
-- Conventions (see .agents/skills/lab-db-guardrails): snake_case, UUID primary keys,
-- timestamptz everywhere, JSONB for lab files / test specs / rubric payloads.
-- Run once as the schema owner:  psql "$ADMIN_DATABASE_URL" -f database/001_schema.sql
-- =====================================================================================
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------- departments
CREATE TABLE IF NOT EXISTS departments (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             text        NOT NULL,
    code             text        NOT NULL UNIQUE,
    institution_name text        NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- users (RBAC)
CREATE TABLE IF NOT EXISTS users (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text        NOT NULL,
    password_hash text        NOT NULL,
    full_name     text        NOT NULL,
    role          text        NOT NULL CHECK (role IN ('student', 'faculty', 'hod')),
    department_id uuid        NOT NULL REFERENCES departments (id) ON DELETE RESTRICT,
    roll_number   text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_roll_only_for_students CHECK (role = 'student' OR roll_number IS NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uidx ON users (lower(email));
CREATE INDEX IF NOT EXISTS users_department_role_idx ON users (department_id, role);

-- ---------------------------------------------------------------- courses
CREATE TABLE IF NOT EXISTS courses (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid        NOT NULL REFERENCES departments (id) ON DELETE RESTRICT,
    code          text        NOT NULL,
    title         text        NOT NULL,
    semester      smallint    NOT NULL CHECK (semester BETWEEN 1 AND 10),
    faculty_id    uuid        REFERENCES users (id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (department_id, code)
);
CREATE INDEX IF NOT EXISTS courses_faculty_idx ON courses (faculty_id);

CREATE TABLE IF NOT EXISTS course_enrollments (
    course_id   uuid        NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
    student_id  uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    enrolled_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (course_id, student_id)
);
CREATE INDEX IF NOT EXISTS course_enrollments_student_idx ON course_enrollments (student_id);

-- ---------------------------------------------------------------- practicals
CREATE TABLE IF NOT EXISTS practicals (
    id            uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id     uuid             NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
    title         text             NOT NULL,
    description   text             NOT NULL DEFAULT '',
    lab_type      text             NOT NULL CHECK (lab_type IN ('coding', 'circuit', 'notebook', 'worksheet')),
    language      text             NOT NULL,
    starter_files jsonb            NOT NULL DEFAULT '{}'::jsonb,
    test_cases    jsonb            NOT NULL DEFAULT '[]'::jsonb,
    rubric        jsonb            NOT NULL DEFAULT '[]'::jsonb,
    max_score     double precision NOT NULL DEFAULT 10 CHECK (max_score > 0),
    due_at        timestamptz,
    status        text             NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    proctored     boolean          NOT NULL DEFAULT true,
    lockdown_mode text             NOT NULL DEFAULT 'off' CHECK (lockdown_mode IN ('off', 'exam', 'seb')),
    seb_config_key text,                      -- SHA-256 hex SEB Config Key (staff-only; never sent to students)
    seb_config_url text,                      -- hosted .seb file; students get a seb:// / sebs:// launch link
    worksheet     jsonb,                      -- worksheet labs: steps / observation table / virtual instrument layout
    created_by    uuid             REFERENCES users (id) ON DELETE SET NULL,
    created_at    timestamptz      NOT NULL DEFAULT now(),
    updated_at    timestamptz      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS practicals_course_status_idx ON practicals (course_id, status);

-- Autosaved student work-in-progress (zero-setup: resume on any device)
CREATE TABLE IF NOT EXISTS practical_drafts (
    practical_id uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id   uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    files        jsonb       NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (practical_id, student_id)
);

-- ---------------------------------------------------------------- submissions
CREATE TABLE IF NOT EXISTS submissions (
    id               uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    practical_id     uuid             NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id       uuid             NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    files            jsonb            NOT NULL,
    status           text             NOT NULL DEFAULT 'graded' CHECK (status IN ('graded', 'reviewed')),
    tests_passed     integer          NOT NULL DEFAULT 0 CHECK (tests_passed >= 0),
    tests_total      integer          NOT NULL DEFAULT 0 CHECK (tests_total >= 0),
    test_results     jsonb            NOT NULL DEFAULT '[]'::jsonb,
    rubric_score     double precision CHECK (rubric_score >= 0),
    max_score        double precision NOT NULL DEFAULT 10,
    rubric_breakdown jsonb            NOT NULL DEFAULT '[]'::jsonb,
    ai_feedback      text,
    grading_model    text,
    faculty_score    double precision CHECK (faculty_score >= 0),
    faculty_comment  text,
    integrity        jsonb,                         -- academic-integrity report (faculty/HOD only)
    submitted_at     timestamptz      NOT NULL DEFAULT now(),
    graded_at        timestamptz,
    reviewed_at      timestamptz
);
CREATE INDEX IF NOT EXISTS submissions_practical_idx ON submissions (practical_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS submissions_student_idx ON submissions (student_id, submitted_at DESC);

-- ---------------------------------------------------------------- execution logs
CREATE TABLE IF NOT EXISTS execution_logs (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    practical_id uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id   uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    lab_type     text        NOT NULL CHECK (lab_type IN ('coding', 'circuit', 'notebook', 'worksheet')),
    mode         text        NOT NULL CHECK (mode IN ('run', 'test')),
    engine       text        NOT NULL,
    status       text        NOT NULL,
    files        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    stdout       text        NOT NULL DEFAULT '',
    stderr       text        NOT NULL DEFAULT '',
    test_results jsonb       NOT NULL DEFAULT '[]'::jsonb,
    tests_passed integer     NOT NULL DEFAULT 0,
    tests_total  integer     NOT NULL DEFAULT 0,
    duration_ms  integer     NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS execution_logs_latest_idx
    ON execution_logs (practical_id, student_id, mode, created_at DESC);
CREATE INDEX IF NOT EXISTS execution_logs_practical_time_idx ON execution_logs (practical_id, created_at);

-- ---------------------------------------------------------------- AI tutor hint audit trail
CREATE TABLE IF NOT EXISTS ai_hint_logs (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    practical_id uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id   uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    execution_id uuid        REFERENCES execution_logs (id) ON DELETE SET NULL,
    focus_test   text,
    hint_level   smallint    NOT NULL CHECK (hint_level BETWEEN 1 AND 3),
    question     text,
    hint_text    text        NOT NULL,
    model        text        NOT NULL,
    source       text        NOT NULL CHECK (source IN ('gemini', 'fallback')),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_hint_logs_practical_student_idx ON ai_hint_logs (practical_id, student_id);

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
                     'context_menu_blocked', 'devtools_blocked', 'focus_lost', 'fullscreen_exit', 'large_insertion',
                     'exam_locked', 'exam_unlocked')),
    detail       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    occurred_at  timestamptz NOT NULL,                 -- client clock (clamped server-side)
    created_at   timestamptz NOT NULL DEFAULT now()    -- server clock
);
CREATE INDEX IF NOT EXISTS proctoring_events_practical_student_idx
    ON proctoring_events (practical_id, student_id, occurred_at);

-- ---------------------------------------------------------------- exam lockdown (one row per student per practical)
CREATE TABLE IF NOT EXISTS exam_attempts (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    practical_id      uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id        uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status            text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'locked', 'submitted')),
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
    paused_at         timestamptz,             -- on a declared break (Pause button) since
    breaks_used       integer     NOT NULL DEFAULT 0,
    break_ms          bigint      NOT NULL DEFAULT 0,
    UNIQUE (practical_id, student_id)
);
CREATE INDEX IF NOT EXISTS exam_attempts_locked_idx ON exam_attempts (practical_id) WHERE status = 'locked';

COMMIT;
