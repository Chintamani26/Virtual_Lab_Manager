---
name: lab-db-guardrails
description: Rules for any change touching the Virtual Lab Manager database schema, SQL, seed data or the repository layer (backend/app/db). Load before writing migrations, queries or new tables.
---

# Lab DB guardrails

## Source of truth
- Schema: `database/001_schema.sql`. Seed: `database/002_seed.sql` is **generated** by
  `backend/scripts/generate_seed_sql.py` from `backend/app/db/seed_data.py` — edit the Python, regenerate, never hand-edit the SQL.
- Least-privilege role: `database/003_app_role.sql` (SELECT/INSERT/UPDATE only, no DELETE, no DDL).
- Domain records: `backend/app/models.py` must mirror table columns 1:1.

## Naming & types
- snake_case, plural table names: `users`, `courses`, `course_enrollments`, `practicals`, `practical_drafts`,
  `submissions`, `execution_logs`, `ai_hint_logs`, `departments`.
- Every primary key is `uuid` (`gen_random_uuid()` default; seed uses stable uuid5).
- Timestamps are `timestamptz`; Python always uses timezone-aware UTC (`app.models.utcnow`).
- Lab files, test specs, rubrics and results are `jsonb`. Scores are `double precision`.
- Enumerations are `text` + `CHECK (... IN (...))` (no Postgres ENUM types — easier migrations).

## Strict role isolation (enforced in the API, `backend/app/deps.py`)
- **student**: only *published* practicals of courses they are enrolled in; only their own drafts,
  executions, hints and submissions. Hidden tests are never serialized to students.
- **faculty**: only courses where `courses.faculty_id = user.id`.
- **hod**: everything inside their own `department_id`, nothing outside.
- Return 404 (not 403) when a student probes a resource they can't see, to avoid leaking existence.

## Query rules
- asyncpg with positional parameters only (`$1`, `$2`…). Never interpolate user input into SQL.
- New repository methods go on `Repository` (`db/base.py`) and BOTH implementations (`memory.py`, `postgres.py`).
- Analytics listings must not fetch heavy columns (`files`, `stdout`, `stderr`).
- The AI layer never generates or executes SQL; HOD analytics read a computed snapshot.

## Process
- Agents/LLMs do not run DDL or write queries against shared databases. Produce SQL files and hand them
  to a human to apply (`psql -f`). Read-only SELECTs for debugging are fine.
- Validate SQL syntax offline (e.g. `pglast.parse_sql`) before handing it over.
