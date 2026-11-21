-- =====================================================================================
-- Least-privilege application role for the FastAPI backend.
-- The API only needs SELECT / INSERT / UPDATE — no DELETE, no DDL.
-- Replace the password placeholder, run as an admin, then use this role in DATABASE_URL:
--   postgresql://vlm_app:<password>@<host>:5432/<db>
-- (Supabase: run in the SQL editor; AlloyDB/Cloud SQL: run via psql as the postgres user.)
-- =====================================================================================
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlm_app') THEN
        CREATE ROLE vlm_app LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO vlm_app;

GRANT SELECT ON departments TO vlm_app;
GRANT SELECT ON users TO vlm_app;
GRANT SELECT ON course_enrollments TO vlm_app;
GRANT SELECT, UPDATE ON courses TO vlm_app;                 -- HOD assigns faculty
GRANT SELECT, INSERT, UPDATE ON practicals TO vlm_app;
GRANT SELECT, INSERT, UPDATE ON practical_drafts TO vlm_app;
GRANT SELECT, INSERT, UPDATE ON submissions TO vlm_app;
GRANT SELECT, INSERT ON execution_logs TO vlm_app;          -- append-only audit
GRANT SELECT, INSERT ON ai_hint_logs TO vlm_app;            -- append-only audit
GRANT SELECT, INSERT, UPDATE ON proctoring_sessions TO vlm_app;
GRANT SELECT, INSERT ON proctoring_events TO vlm_app;       -- append-only audit
GRANT SELECT, INSERT, UPDATE ON exam_attempts TO vlm_app;

COMMIT;
