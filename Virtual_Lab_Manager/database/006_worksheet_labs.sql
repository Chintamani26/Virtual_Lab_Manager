-- =====================================================================================
-- Migration v1.3: worksheet labs (step-by-step maths problems and virtual experiments, no code).
-- Needed for databases created before this version (fresh installs get it from 001_schema.sql).
-- Run AFTER 005:  psql "$ADMIN_DATABASE_URL" -f database/006_worksheet_labs.sql
-- Then re-apply the regenerated 002_seed.sql if you want the new seeded labs (it skips rows that already exist).
-- =====================================================================================
BEGIN;

ALTER TABLE practicals ADD COLUMN IF NOT EXISTS worksheet jsonb;

ALTER TABLE practicals DROP CONSTRAINT IF EXISTS practicals_lab_type_check;
ALTER TABLE practicals ADD CONSTRAINT practicals_lab_type_check
    CHECK (lab_type IN ('coding', 'circuit', 'notebook', 'worksheet'));

ALTER TABLE execution_logs DROP CONSTRAINT IF EXISTS execution_logs_lab_type_check;
ALTER TABLE execution_logs ADD CONSTRAINT execution_logs_lab_type_check
    CHECK (lab_type IN ('coding', 'circuit', 'notebook', 'worksheet'));

COMMIT;
