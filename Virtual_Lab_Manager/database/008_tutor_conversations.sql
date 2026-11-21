-- =====================================================================================
-- Migration v1.5: AI Lab Tutor conversations (backend/app/ai/tutor_chat.py).
-- One row per chat message. The full history is kept for faculty review; the API sends the
-- model only the newest 6 messages. Needed for every PostgreSQL database (new table).
-- Run AFTER 007:  psql "$ADMIN_DATABASE_URL" -f database/008_tutor_conversations.sql
-- =====================================================================================
BEGIN;

CREATE TABLE IF NOT EXISTS ai_tutor_messages (
    seq          bigserial   PRIMARY KEY,                -- insertion order (two messages can share created_at)
    id           uuid        NOT NULL UNIQUE,
    practical_id uuid        NOT NULL REFERENCES practicals (id) ON DELETE CASCADE,
    student_id   uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role         text        NOT NULL CHECK (role IN ('student', 'tutor')),
    action       text        NOT NULL CHECK (action IN ('chat', 'explain_error', 'explain_test', 'explain_concept',
                                                        'next_hint', 'concept_check')),
    message      jsonb       NOT NULL,                   -- the full TutorMessage (content, flags, model, ...)
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_tutor_messages_practical_student_idx
    ON ai_tutor_messages (practical_id, student_id, seq);

-- least-privilege app role (003_app_role.sql): append-only audit, like ai_hint_logs
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlm_app') THEN
        GRANT SELECT, INSERT ON ai_tutor_messages TO vlm_app;
        GRANT USAGE ON SEQUENCE ai_tutor_messages_seq_seq TO vlm_app;
    END IF;
END
$$;

COMMIT;
