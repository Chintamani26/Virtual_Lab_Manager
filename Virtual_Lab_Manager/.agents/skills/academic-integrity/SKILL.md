---
name: academic-integrity
description: Rules for proctored labs and AI-generated / copied code detection. Load before touching backend/app/ai/integrity.py, the proctoring endpoints, or the student workspace's copy/paste and telemetry code.
---

# Proctoring & academic integrity

## What exists
- **Proctored labs** (`practicals.proctored`, default on; faculty toggle). The workspace shows a start gate
  (fullscreen), blocks copy/cut/paste/drag-drop/right-click/devtools shortcuts, and records tab switches,
  fullscreen exits and typing telemetry → `POST /api/student/practicals/{id}/proctor/events`.
- **Sessions** (`proctoring_sessions`): one per page load; `baseline_files` is captured **server-side** when the
  session is created — never trust a client-supplied baseline. Latest cumulative typing stats live here.
- **Events** (`proctoring_events`): append-only audit of blocked actions, focus loss, bulk insertions.
- **Integrity report** (`submissions.integrity`) computed at submit time by `app/ai/integrity.py`:
  behavioural evidence + Gemini/heuristic content review + line-similarity vs classmates.

## Exam lockdown (`practicals.lockdown_mode`: off | exam | seb) — `backend/app/services/exam.py`
- One tab per exam: `exam_attempts.active_session_id`. Every run/lint/hint/draft/submit must carry
  `X-Exam-Session`; `exam.enforce()` returns 409/423/403. Never add a student write endpoint without it.
- Leaving (focus loss, fullscreen exit, devtools, 2nd tab, reload/close = `page_closed` keepalive) locks; only
  faculty/HOD unlock. Only the tab holding the exam can lock it / add a violation (stale tabs are ignored).
- Frontend: `lib/useExamLockdown.ts` (phase machine + detectors + `X-Exam-Session`/SEB headers via
  `registerExamHeaders`), screens in `components/workspace/ExamLockdown.tsx`. Map 423/409/403 to the lock screens,
  never to toasts; never use `window.confirm` in the workspace (it exits fullscreen → locks the exam).
- SEB: verify SHA-256(url-without-fragment + Config Key) from the JS-API headers (page URL must be this
  practical's lab page on an allowed origin) or the native `X-SafeExamBrowser-ConfigKeyHash` header.
  `seb_config_key` is staff-only — never serialize it to students (they could forge hashes).
- Be honest: web exam mode cannot stop a second device; only SEB gives OS-level lockdown.

## Non-negotiable rules
1. **Indicators, not verdicts.** Never auto-penalise, auto-zero or block a submission on integrity signals.
   The report is for faculty review; UI copy must say "indicators for review — not proof".
2. **Integrity is never shown to students** (`include_integrity=False` in every student endpoint).
3. Students must be told the lab is proctored *before* the session starts (gate overlay lists what is recorded).
4. Keep reasons human-readable with numbers ("Only 60 characters were typed, but the submission adds 1,400").
5. Content-only evidence must stay conservative: clean/correct code is not evidence. Weight behavioural
   evidence (typed ratio, bulk insertions, no session) above stylometry.
6. Synthetic seed submissions (`grading_model == "synthetic-seed"`) are excluded from peer comparison with live work.

## Limits (be honest in docs/pitch)
Browser-side blocking can be bypassed (second device, retyping, browser extensions, modified clients); typing
stats are client-reported. That is why everything is recorded server-side and combined into evidence rather
than relied on as prevention. AI-text detectors are unreliable; there is no certainty in either direction.

## Tuning
Thresholds/weights live at the top of `build_report()`: typed ratio < 0.3 (critical) / < 0.6, bulk insert
≥ 60 chars, burst > 30 cps, similarity ≥ 0.95 / ≥ 0.85 on ≥ 300 chars of student-written lines,
risk ≥ 60 high / ≥ 30 medium. Add a test in `backend/tests/test_integrity.py` for every change.
