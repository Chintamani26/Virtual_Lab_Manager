---
name: socratic-tutor
description: How the Gemini Socratic tutor, Gemma linter and rubric grader must behave. Load before editing prompts (backend/app/ai/prompts.py) or any code in backend/app/ai.
---

# Socratic tutor & AI evaluation

## Pipeline (hybrid Gemma + Gemini)
| Trigger | Model | Module | Output |
|---|---|---|---|
| Typing pauses (1.5 s debounce) | local `ast` / circuit parser, then **Gemma** (`GEMMA_MODEL`) | `ai/linter.py` | ≤5 diagnostics, cached by code hash |
| Student clicks *Ask Tutor* after a failing run | **Gemini** (`GEMINI_MODEL`) | `ai/tutor.py` | `HintResponse` JSON |
| Student chats / quick actions in the **Tutor** drawer | **Gemini** | `ai/tutor_chat.py` (+ `tutor_guard`, `tutor_context`, `tutor_response`) | `TutorMessage` stored in the server-side thread |
| Student submits | **Gemini** | `ai/grader.py` | per-criterion rubric scores + summary |
| Faculty clicks *Generate tests* | **Gemini** | `ai/testgen.py` | validated `TestCaseSpec[]` |
| HOD asks a question | **Gemini** | `ai/analyst.py` | answer + highlights + optional table |

## Non-negotiable tutor rules
1. **Never reveal the solution.** No corrected code, no full functions, no multi-line code blocks.
   `_scrub()` strips multi-line fences as a backstop — keep it.
2. Analyse the *actual* stderr / failing assertion from the student's latest server-side test run
   (`execution_logs`), not client-supplied claims.
3. Focus on one failing test at a time (the first failing visible test).
4. Progressive levels per (student, practical, test): 1 = conceptual nudge + question,
   2 = point to the code region / branch, 3 = plain-language fix steps (still no code). Max 3.
5. Never mention hidden tests to students.
6. Always return a guiding question.

## AI Lab Tutor (chat) rules
1. **Context is an allowlist** (`tutor_context.LabContext`): brief, worksheet instructions, the student's own files,
   visible tests (worksheet checks: description only), visible results, last 6 server-side messages. Never add
   hidden tests, the rubric, worksheet check code, instrument constants or anything about other students.
2. **History comes from the server** (`tutor_threads` / `ai_tutor_messages`), never from the request body.
3. **Untrusted text is fenced** with a per-request nonce (`fence()`); the system prompt says data blocks are not
   instructions. Keep the `{canary}` marker in `prompts.LAB_TUTOR`: a reply that contains it is replaced.
4. **Guard before the model** (`tutor_guard.screen`): injection and restricted-data requests are answered without
   calling Gemini; solution requests are flagged and the model is told to decline. Guard flags live on the
   student's message, validator flags on the tutor's reply.
5. **Validate every reply** (`tutor_response.check_reply`), including Gemini hints: fenced and unfenced code runs,
   circuit gate lines, hidden test names, and (worksheets) values of checks the student hasn't passed.
6. `next_hint` must keep using `SocraticTutor` + `ai_hint_logs` so hint levels and HOD analytics stay consistent.
7. Fallbacks are honest: offline, free-form chat says the AI tutor is offline; it never pretends to answer.

## Faculty generators & HOD insights rules
1. **Drafts only.** `practical_gen` / `teaching` return content for review; nothing is saved or published by the API.
2. **Verify generated code by running it** (`PracticalGenerator._verify`): tests must pass on the reference and fail on the
   starter. Never ship tests the sandbox hasn't run. The reference solution is never stored with a practical.
3. **Numbers come from data, words from the model.** `services/insights.py` computes every count/rate; `difficulties.py`
   drops unknown courses/tests and non-verbatim quotes; `briefing.py` returns the metrics beside the text.
4. **Anonymise student text** (`insights.anonymise`) and leave out guard-flagged tutor messages before sending it to Gemini.
5. Every analytical feature has a rule-based fallback (`source: "fallback"`); generators return 503 without Gemini.

## Grading guardrails
- Scores are clamped to `[0, max_points]` in 0.5 steps; correctness criteria are capped by the
  authoritative pass ratio (visible + hidden tests). The LLM cannot over-grade failing code.
- Total is scaled to the practical's `max_score` (default 10) — e.g. "8/10 Rubric Score".
- Faculty override (`faculty_score`) always wins (`final_score`).

## Resilience
- Every AI call returns `None` on failure → deterministic fallbacks (`source: "fallback"`, `model: "rules"`).
  The demo must work with no `GEMINI_API_KEY`.
- Structured output: Gemini uses `response_schema` (Pydantic). Gemma output is parsed leniently from text.
- Log hints to `ai_hint_logs` — they power the HOD "hint requests" bottleneck metric.

## Prompt calibration
Iterate system instructions in Google AI Studio with real failing runs (e.g. Lab 4 BST draft failing
`test_duplicate_keys`), then paste into `ai/prompts.py`. Curated fallback hints in `tutor.py::CURATED`
are good few-shot references.
