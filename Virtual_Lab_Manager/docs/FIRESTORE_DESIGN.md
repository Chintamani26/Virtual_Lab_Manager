# Virtual Lab Manager: Cloud Firestore data design (and the Google stack around it)

Status: **implemented**. What is in place:
- **Backend:** `backend/app/db/firestore.py` and `backend/app/firebase_auth.py`, switched on with
  `STORAGE=firestore AUTH_PROVIDER=firebase`.
- **Seed:** `scripts/seed_firestore.py`.
- **Frontend:** `frontend/src/lib/firebase.ts`, giving Firebase sign-in and `exam_live` real-time listeners.
- **Project `vlm-buildathon`:** the rules and all 14 indexes are deployed, and the read-only
  `scripts.check_firestore_indexes` passes 29/29 query shapes.

The in-memory store stays in place for offline demos and tests. Setup and run steps are in the README
section "Firebase mode".

This document defines how **Cloud Firestore** replaces PostgreSQL as the production database, and which
other Google services we adopt, in what order.

Companion files:
- `firebase/firestore.rules`: security rules.
- `firebase/firestore.indexes.json`: composite indexes and index exemptions.
- `firebase.json`: Firebase CLI config for rules, indexes and emulators.

---

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| Database | **Cloud Firestore, Native mode, Standard edition, `(default)` database** | The "Firebase database". It is serverless, needs no connection pool on Cloud Run, has real-time listeners (instant exam lock/unlock) and strongly consistent transactions. |
| Not chosen | Firebase Realtime Database (as the main store) | A single JSON tree with weak querying. It may come back later only for exam *presence* (see §8). |
| Not chosen | Firebase Data Connect | It is Cloud SQL PostgreSQL underneath, so it gives no real-time or serverless benefit over what we already have. |
| Location | **`asia-south1` (Mumbai)** | Keeps student data in India and gives the lowest latency for Indian colleges. **The location can't be changed after the database is created.** |
| Who writes | **Only the FastAPI backend**, through the Firebase Admin SDK, which bypasses rules | All business rules stay in one tested place: grading, hidden tests, exam enforcement, integrity. Browsers never write to Firestore. |
| Who reads directly | Browsers read **two** things, read-only and in real time: their own `users/{id}` and `exam_live` | Instant lock/unlock and a live monitor, without exposing code, hidden tests, grades or integrity reports. |
| Field and collection naming | **snake_case**, the same names as the Pydantic records and SQL tables | Documents are `Record.model_dump()` / `Record.model_validate(doc)`, so no mapping layer is needed. |
| Document IDs | The same UUIDs as today. Seed IDs stay deterministic `uuid5`. Join tables use `{a}__{b}`. | The in-memory store, PostgreSQL and Firestore share IDs, the seed is reused, and links stay stable. |
| Auth | **Firebase Authentication**. Custom claims `{role, department_id, app_uid}`. | It replaces our PBKDF2 passwords and JWTs in production, and adds Google Sign-In (see §7). |
| Code seam | A new `FirestoreRepository` implementing `backend/app/db/base.py::Repository` | Routers and services don't change. `STORAGE=memory|postgres|firestore`. |
| PostgreSQL | It stays in the repo but gets no new features. Delete it once Firestore is verified. | This avoids keeping three stores in sync. |

---

## 2. Collection catalog

```
departments/{department_id}
users/{user_id}                                   ← browser: get own doc
courses/{course_id}
course_enrollments/{course_id}__{student_id}
practicals/{practical_id}                         ← server-only (hidden tests, SEB key)
practical_drafts/{practical_id}__{student_id}
submissions/{submission_id}                       ← server-only (integrity report)
execution_logs/{execution_id}                     (TTL)
ai_hint_logs/{hint_id}
proctoring_sessions/{session_id}                  (TTL)
proctoring_events/{event_id}                      (TTL, append-only)
exam_attempts/{practical_id}__{student_id}        ← server-only (holds the tab's claim token)
exam_live/{practical_id}__{student_id}            ← browser: real-time, read-only mirror
tutor_threads/{practical_id}__{student_id}        ← server-only (AI Lab Tutor conversation)
```

All collections are top-level. Subcollections were considered and rejected: every important query cuts
across a parent (for example "all submissions for these practicals" or "all events for this student").
Top-level collections keep those queries simple, keep the repository a 1:1 port, and keep the BigQuery
export flat.

### 2.1 Field reference

The types use Firestore names: `ts` = timestamp, `map<path, code>` = map of file name to source.
**Bold** marks a field that doesn't exist in SQL today: it is either denormalized for a query or rule, or
needed for retention.

| Collection | Doc ID | Fields | Written by | Read by |
|---|---|---|---|---|
| `departments` | uuid | name, code, institution_name, **hod_ids[]**, created_at | seed/admin | server |
| `users` | uuid (= Firebase Auth uid for provisioned accounts) | email, **email_lower**, full_name, role (`student`\|`faculty`\|`hod`), department_id, roll_number\|null, **auth_provider**, created_at. *No password_hash in Firestore mode.* | seed / roster import | server; browser: own doc |
| `courses` | uuid | department_id, code, title, semester, faculty_id\|null, created_at | seed, HOD assign | server |
| `course_enrollments` | `{course_id}__{student_id}` | course_id, student_id, **department_id**, enrolled_at | seed / roster import | server |
| `practicals` | uuid | course_id, **department_id**, title, description, lab_type, language, starter_files map, test_cases[] (incl. `hidden`), rubric[], max_score, due_at, status, proctored, lockdown_mode, seb_config_key, seb_config_url, created_by, created_at, updated_at | faculty API | server only |
| `practical_drafts` | `{practical_id}__{student_id}` | practical_id, student_id, files map, updated_at | student API (autosave) | server |
| `submissions` | uuid | practical_id, student_id, files, status, tests_passed, tests_total, test_results[], rubric_score, max_score, rubric_breakdown[], ai_feedback, grading_model, faculty_score, faculty_comment, integrity map, submitted_at, graded_at, reviewed_at | student submit, faculty review | server only |
| `execution_logs` | uuid | practical_id, student_id, lab_type, mode, engine, status, files, stdout, stderr, test_results[], tests_passed, tests_total, duration_ms, created_at, **expire_at** | run/test API | server |
| `ai_hint_logs` | uuid | practical_id, student_id, execution_id, focus_test, hint_level, question, hint_text, model, source, created_at | hint API | server |
| `proctoring_sessions` | client UUID (one per page load) | practical_id, student_id, baseline_files (server-captured), stats map, started_at, last_seen_at, **counts map** (§5), **expire_at** | proctor API | server |
| `proctoring_events` | uuid | practical_id, student_id, session_id, event_type, detail map, occurred_at, created_at, **expire_at** | proctor/exam API | server |
| `exam_attempts` | `{practical_id}__{student_id}` | all `ExamAttemptRecord` fields, including **active_session_id** | exam API (transactions) | server only |
| `exam_live` | `{practical_id}__{student_id}` | practical_id, student_id, student_name, course_id, department_id, **staff_ids[]**, status, lock_reason, violations, locked_at, unlocked_at, submitted_at, updated_at | exam API (same transaction) | browser (rules), server |
| `tutor_threads` | `{practical_id}__{student_id}` | practical_id, student_id, messages[] (role, action, content, guiding_question, concept, hint_level, focus_test, understanding, expects_answer, flags[], model, source, execution_id, created_at), dropped, created_at, updated_at | tutor API (transaction: read, append, keep the newest 200 messages) | server only |

### 2.2 Why `exam_attempts` and `exam_live` are separate

Firestore rules work on whole documents and can't hide individual fields. `exam_attempts.active_session_id`
is the secret that lets exactly one browser tab work on the exam. If a student could read it, a second tab
could copy it and bypass one-tab enforcement.

So the server keeps that secret in `exam_attempts`, which browsers can never read. It mirrors only safe,
display-only fields into `exam_live`, which browsers subscribe to. Both documents are written **in the same
transaction**, so the mirror can't drift.

`exam_live` is written only when the status changes: start, lock, unlock or submit. Heartbeats never touch
it, so faculty listeners stay quiet and cheap.

---

## 3. Integrity constraints Firestore doesn't enforce

Firestore has no foreign keys, unique constraints or CHECK constraints. Each SQL guarantee moves to a
named place:

| SQL guarantee | Firestore equivalent |
|---|---|
| `users.email` unique (lower) | Firebase Auth enforces one account per email. `email_lower` is queried before provisioning. |
| `courses (department_id, code)` unique | New course IDs are `uuid5(department_id + code)`, so a duplicate would collide on create. |
| Enrollment primary key | The document ID `{course_id}__{student_id}` makes duplicates impossible. |
| One exam attempt per student per practical | The document ID `{practical_id}__{student_id}`. |
| CHECK / enum columns | The Pydantic `Literal` types are validated on every write, because all writes go through the API. |
| `ON DELETE CASCADE` | Nothing is hard-deleted in normal use. Archiving is a status. TTL handles logs (§6). |
| Roll number only for students | Pydantic validator on `UserRecord`. |

---

## 4. Query → index map

The left column is every `Repository` method. `in` filters are chunked to 30 values, which is Firestore's
limit. All of these indexes are in `firebase/firestore.indexes.json`.

| Repository method / client listener | Firestore query | Index |
|---|---|---|
| `get_user_by_email` | `users` where `email_lower ==` limit 1 | auto |
| `list_users(department_id, role)` | `users` where `department_id ==` [and `role ==`] | composite (department_id, role) |
| `get_users(ids)` | `get_all(refs)` | — |
| `list_courses(department_id \| faculty_id)` | `courses` where `department_id ==` / `faculty_id ==` | auto |
| `list_courses(student_id)` | `course_enrollments` where `student_id ==`, then `get_all(courses)` | auto |
| `list_enrollments(course_ids)` | `course_enrollments` where `course_id in [...]` | auto |
| `list_practicals(course_ids, published_only)` | `practicals` where `course_id in [...]` [and `status == "published"`] | composite (course_id, status) |
| `get_draft` / `upsert_draft` | doc get / set | — |
| `list_submissions(practical_ids)` | where `practical_id in [...]` order by `submitted_at desc` | composite (practical_id, submitted_at desc) |
| `list_submissions(student_id)` | where `student_id ==` order by `submitted_at desc` | composite (student_id, submitted_at desc) |
| `list_submissions(both)` | where `student_id ==` and `practical_id in [...]` order by `submitted_at desc` | composite (student_id, practical_id, submitted_at desc) |
| `get_latest_execution` | where `practical_id ==`, `student_id ==`, `mode ==` order by `created_at desc` limit 1 | composite (practical_id, student_id, mode, created_at desc) |
| `list_execution_logs(practical_ids, since)` | where `practical_id in [...]` and `created_at >= since`, with a field projection (`select`) that skips files/stdout | composite (practical_id, created_at) |
| `list_hint_logs(...)` | where `practical_id in [...]` [and `student_id ==`] | composite (student_id, practical_id) |
| `list_proctor_events(p, s)` | where `practical_id ==`, `student_id ==` order by `occurred_at` | composite (practical_id, student_id, occurred_at) |
| `list_practical_proctor_events(p)` | where `practical_id ==` order by `occurred_at` | composite (practical_id, occurred_at) |
| `list_proctor_sessions(p, s)` | where `practical_id ==`, `student_id ==` order by `started_at` | composite (practical_id, student_id, started_at) |
| `list_practical_proctor_sessions(p)` | where `practical_id ==` | auto |
| `get/save_exam_attempt` | doc get / **transaction** (§5) | — |
| `list_exam_attempts(practical_ids)` | where `practical_id in [...]` | auto |
| Browser: alert bell | `exam_live` where `staff_ids array-contains me` and `status == "locked"` | composite (staff_ids contains, status) |
| Browser: Live Lab Monitor | `exam_live` where `practical_id == p` and `staff_ids array-contains me` | composite (practical_id, staff_ids contains) |
| Browser: student's lock screen | `onSnapshot(exam_live/{p}__{me})` | — |
| Server: faculty reassigned | `exam_live` where `course_id ==` and `status in [active, locked]` | composite (course_id, status) |

**Index exemptions.** These fields are never filtered on, so they are excluded from single-field indexing:
code maps, stdout/stderr, test results, integrity, rubric, baselines and event details. This cuts index
writes and storage roughly in half, and avoids the 40,000-index-entries-per-document limit on large code
maps.

---

## 5. Transactions, counters and write paths

| Operation | Firestore mechanism |
|---|---|
| Exam start / claim tab, violation, mentor unlock / lock, submit | One **transaction**: read `exam_attempts/{p}__{s}`, then write `exam_attempts`, `exam_live` and the `exam_locked`/`exam_unlocked` event. The server SDK locks the documents, so two tabs racing to claim the exam can't both win. *Today's PostgreSQL path doesn't lock this row; Firestore fixes that.* |
| Submit | The `submissions` create and `exam.mark_submitted` happen in one transaction. |
| Proctor event batch | One **batched write**: the events, plus a `FieldValue.increment` on `proctoring_sessions.counts.<type>` and `counts.time_away_ms`. The Live Lab Monitor reads the counters instead of scanning every event, which makes each poll about 60 document reads instead of thousands. |
| Faculty reassigned (`set_course_faculty`) | Update the course, then batch-update `staff_ids` on its open `exam_live` documents (500 per batch). |
| Exam heartbeat | Write `last_heartbeat_at` only if the stored value is more than 15 s old. That is one write per student every ~15 s, not every 5 s; "online" is computed as seen within the last 30 s. |
| Draft autosave | `set` on one document. The ~1 write/s sustained limit per document is well above the autosave rate. |

**Repository change this requires:** add `update_exam_attempt(practical_id, student_id, mutate) -> ExamAttemptRecord`:
- The in-memory store uses an `asyncio.Lock`.
- PostgreSQL uses `SELECT … FOR UPDATE`.
- Firestore uses `@async_transactional`.

`services/exam.py` will call it instead of get-then-save.

**Size limits.**
- A document can be at most 1 MiB.
- `stdout`/`stderr` are capped at 64 KB each before they are stored.
- Code files are already capped by the request schema.
- Notebooks larger than ~700 KB should go to Cloud Storage (§8, tier 2).

---

## 6. Retention, backup, privacy

- **TTL policies:** `expire_at` is set on write. It is 180 days for `proctoring_events`,
  `proctoring_sessions` and `execution_logs`. Grades, submissions and hints are kept for the academic
  record. This is data minimisation for behavioural telemetry and supports the institution's obligations
  under India's DPDP Act. It is not legal advice; the college's policy decides the number.
- **Point-in-time recovery** (7 days) and a **daily backup schedule** (14-day retention).
- **Region:** everything stays in `asia-south1`.
- **Students never read integrity data:** it lives only in server-only documents, and the API never
  serialises it for students. `include_integrity=False` is already tested.

---

## 7. Auth (Firebase Authentication) as it touches the data model

1. **Provisioning.** The seed or roster import creates the Firebase Auth user with
   **`uid = users/{id}`**, so the IDs match. Demo accounts use email/password (`demo1234`) with
   `email_verified = true`.
2. **Sign-in.**
   - The browser uses the Firebase JS SDK: one-click demo login, or **Sign in with Google** restricted
     to the institution's domain (the `hd` parameter, re-checked on the server).
   - It sends the Firebase ID token to the API.
3. **First call: `POST /api/auth/session`.**
   - The server verifies the token (`firebase_admin.auth.verify_id_token(check_revoked=True)`).
   - It finds `users` by the verified `email_lower`. There is **no self-registration**: the account must
     already be provisioned.
   - It sets the custom claims `{role, department_id, app_uid}`.
   - The browser then refreshes the token once.
   - `app_uid` exists because accounts that first sign in with Google may get a different Auth uid.
     Rules and the API always use `app_uid`.
4. **Role change.** Update the claims and call `revoke_refresh_tokens`. This replaces today's JWT
   invalidation when a role changes. Rules may honour a stale claim for up to an hour, which is the ID
   token's lifetime. `exam_live` access is also gated by the data-driven `staff_ids` list, so removing a
   faculty member from a course takes effect immediately.
5. **Offline mode.** Local mode (in-memory store + our own JWT) stays for tests and offline demos:
   `AUTH_PROVIDER=local|firebase`.

---

## 8. The Google stack: what we adopt and in what order

Status: ✅ already built, 🔨 planned next, ➕ optional.

**Tier 1: the platform (do these before the demo)**

| Google product | Role in Virtual Lab Manager | Status |
|---|---|---|
| **Cloud Firestore** | Primary database (this document) | 🔨 |
| **Firebase Authentication** | Email/password demo accounts, Google Sign-In for the college domain, custom-claim roles | 🔨 |
| **Firestore real-time listeners** | Instant exam lock/unlock on the student screen, Live Lab Monitor, mentor alert bell (replaces polling) | 🔨 |
| **Gemini API** (Gemini 3.5 Flash-Lite) + **Gemma 4** | Socratic hints, rubric grading, AI test generation, HOD analyst, lint, AI-style integrity review | ✅ |
| **Cloud Run** | FastAPI API | ✅ |
| **Firebase App Hosting** | Next.js frontend (SSR, GitHub rollouts; runs on Cloud Run and Cloud CDN) | 🔨 |
| **Secret Manager** | Gemini key, JWT secret, Judge0 key | ✅ |
| **Cloud Build + Artifact Registry** | Container builds for deploys | ✅ |

**Tier 2: Google features that strengthen the pitch**

| Google product | Role | Status |
|---|---|---|
| **Firestore vector search** + **Gemini embeddings** | Store an embedding of each submission's code (with the starter code removed). Use `find_nearest` to find the most similar classmates. This catches renamed-variable copies that line matching misses. | ➕ |
| **BigQuery** (Firebase extension "Stream Firestore to BigQuery") + **Looker Studio** | Department analytics warehouse and a shareable HOD dashboard. The HOD "ask" feature can run on it later, **read-only**. | ➕ |
| **Firebase Cloud Messaging** | Push notification to the mentor's phone or browser when a student's exam locks | ➕ |
| **Firebase App Check** (reCAPTCHA Enterprise) | Only our web app can call the API; scripted clients are refused | ➕ |
| **Cloud Storage for Firebase** | Lab manuals (PDF), notebook datasets, large notebooks, compliance-report archives | ➕ |
| **Cloud Run sandbox service** | Run student code in a separate, permission-less, no-egress Cloud Run service. This replaces Judge0, so the stack is 100% Google. | ➕ |

**Tier 3: nice to have**
- **Google Classroom API:** import rosters, and push grades for coursework this app created. The API
  only lets an app grade its own coursework.
- **Google Sheets API:** export the compliance report.
- **Cloud Tasks:** asynchronous grading queue. Submit returns instantly, and the scorecard arrives
  through a listener.
- **Cloud Scheduler:** nightly at-risk digest for the HOD.
- **Vertex AI:** run the same `google-genai` SDK with `vertexai=True` for IAM, quotas and regional
  processing. Check model availability in `asia-south1`.
- **Realtime Database presence:** `onDisconnect` for exact online/offline status in exams.
- **Cloud Logging and Error Reporting:** already automatic on Cloud Run.

Pitch advice: the jury rewards Google services that do real work. Tier 1 plus two or three Tier 2 items,
each visible in the demo, beats a long list. Example: the mentor's phone buzzes, they unlock, and the
student's screen updates instantly.

---

## 9. Rough load for one exam (60 students, 3 hours)

| Source | Writes | Reads |
|---|---|---|
| Heartbeats (persisted every 15 s, read every 5 s) | ~43k | ~130k |
| Draft autosave (~1 per 15 s while typing) | ~25–40k | — |
| Runs, hints, proctor batches, submissions | ~10k | ~10k |
| Live Lab Monitor (API every 5 s, counters + listener) | — | ~150k |
| **Total** | **~80–95k** | **~300k** |

Firestore's free tier is 20k writes and 50k reads per day, so a real exam exceeds it. Even so, the paid
cost is on the order of cents per exam. Check current `asia-south1` pricing before quoting a figure.
Demos and development stay inside the free tier.

---

## 10. Setup (commands for a project owner to run)

These need `gcloud` and the Firebase CLI, logged into the team's Google Cloud project.

```bash
# one-time: create the database in Mumbai (location is permanent)
gcloud firestore databases create --location=asia-south1 --type=firestore-native

# rules + indexes from this repo
cp .firebaserc.example .firebaserc        # set your project id
firebase deploy --only firestore:rules,firestore:indexes

# TTL policies
for c in proctoring_events proctoring_sessions execution_logs; do
  gcloud firestore fields ttls update expire_at --collection-group=$c --enable-ttl
done

# recovery
gcloud firestore databases update --database='(default)' --enable-pitr
gcloud firestore backups schedules create --database='(default)' --recurrence=daily --retention=14d

# local development against emulators (no cloud writes)
firebase emulators:start --only firestore,auth
```

Seeding Firestore and Firebase Auth will be done by `backend/scripts/seed_firestore.py`, which is not yet
written. It reuses `app/db/seed_data.py`, so the IDs and demo story are identical. **The project owner runs
it, against the emulator or the real project; the coding assistant does not.**

---

## 11. Implementation plan

1. **`FirestoreRepository`** (`backend/app/db/firestore.py`, `firebase-admin` async client):
   - Implement the `update_exam_attempt` transaction, the `exam_live` mirror and the proctor counters.
   - Set `STORAGE=firestore`.
   - Write contract tests that run the same suite against memory and, when `FIRESTORE_EMULATOR_HOST`
     is set, against the emulator.
   - Write the seed script.
2. **Firebase Auth:** `POST /api/auth/session`, the ID-token dependency, frontend sign-in (demo +
   Google), and `AUTH_PROVIDER`.
3. **Real-time:**
   - The frontend subscribes to `exam_live` for the lock screen, the monitor and the bell, falling back
     to polling in local mode.
   - Rules unit tests with `@firebase/rules-unit-testing`.
4. **Deploy:** Firebase App Hosting for the web app; Cloud Run gets a service account with
   `roles/datastore.user` (no key files; Application Default Credentials).
5. **Tier 2 items,** chosen for the demo.
