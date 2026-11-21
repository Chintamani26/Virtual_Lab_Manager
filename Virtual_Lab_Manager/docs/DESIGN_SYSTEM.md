# Virtual Lab Manager — Design System

"Developer-first academic SaaS": a dark, Linear/Vercel/Replit-style **IDE** for students and a crisp,
light **executive** layout for Faculty and HOD dashboards. Next.js 16 + Tailwind CSS v4 + lucide-react,
no animation libraries (CSS only, `prefers-reduced-motion` respected).

Source of truth: tokens in [`frontend/src/app/globals.css`](../frontend/src/app/globals.css) (`@theme`),
fonts in [`frontend/src/app/layout.tsx`](../frontend/src/app/layout.tsx), primitives in
[`frontend/src/components/ui.tsx`](../frontend/src/components/ui.tsx).

## 1. Tokens

### Typography
| Token | Value | Use |
|---|---|---|
| `font-sans` | **Inter** (`next/font`, `--font-inter`) | all UI text |
| `font-mono` | **JetBrains Mono** (`--font-jetbrains`, also fed to Monaco with ligatures) | code, logs, test names, scores, metrics |

Type scale (Tailwind defaults): 10–11px meta/badges · 12–13px controls, terminal · 14px body · 16–18px dialog titles ·
24–30px scores. Numbers that update (`4/5`, `9.5/10`, counters) use `font-mono tabular-nums` so they never jitter.

### Workspace palette (dark)
| Token | Hex | Utility |
|---|---|---|
| canvas | `#0a0b0f` | `bg-canvas` (app background, terminals) |
| surface-1 | `#0f1117` | `bg-surface-1` (panes, header, Monaco background) |
| surface-2 | `#151821` | `bg-surface-2` (cards, active tabs, menus) |
| surface-3 | `#1c202b` | `bg-surface-3` (secondary buttons, segmented control) |
| line | `rgba(255,255,255,.06)` | `border-line`, `ring-line` (1px hairlines) |
| line-strong | `rgba(255,255,255,.10)` | `border-line-strong` (controls, dividers) |
| fg / fg-muted / fg-faint | `#e6e8ee` / `#9aa3b2` / `#6b7280` | text hierarchy |
| brand / brand-400 / brand-600 | `#6366f1` / `#818cf8` / `#4f46e5` | primary CTA, focus ring, active tab bar |
| ai / ai-400 | `#8b5cf6` / `#a78bfa` | reserved; not used in the minimal UI (see section 6) |

### Dashboards palette (light)
`bg-slate-50` page · white cards · `slate-200` borders · `slate-900` / `slate-600` text · indigo accents
(`Card`, `Badge`, `Button` in `ui.tsx`; recipes in section 6). Dashboards inherit Inter/JetBrains Mono globally.

### Semantic colours
| Meaning | Pill class | Recipe |
|---|---|---|
| pass / success | `pill-pass` | `bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/20` |
| warning / partial | `pill-warn` | amber, same recipe |
| fail / error | `pill-fail` | rose, same recipe |
| info / runtime | `pill-info` | sky, same recipe |
| AI | `pill-ai` | violet, same recipe |
| brand | `pill-brand` | indigo, same recipe |
| neutral | `pill-neutral` | `bg-white/4 text-fg-muted ring-line-strong` |

### Shape, elevation, motion
| Token | Value | Utility |
|---|---|---|
| radius-ctl / card / panel | 6 / 8 / 12px | `rounded-ctl` (buttons, inputs) · `rounded-card` (cards) · `rounded-panel` (dialogs, popovers) |
| shadow-panel | hairline + soft drop | `shadow-panel` |
| shadow-pop | hairline + deep drop | `shadow-pop` (menus, modals, toasts) |
| shadow-glow-brand | indigo glow | primary hover, logo mark |
| focus | 2px brand outline, 2px offset | built into `.btn` |
| motion | 150–200ms `cubic-bezier(.2,.8,.2,1)` | `animate-fade-in` · `animate-rise-in` · `animate-pop-in` · `animate-bar-fill` · `animate-spark` · `.skeleton-dark` shimmer |

## 2. Component patterns (`@layer components`)
- **Buttons** — `.btn` + `.btn-primary` (the one primary action per view: *Submit*), `.btn-secondary`
  (*Run tests*, *Hint*), `.btn-ghost` (*Run*, tertiary). Text only; icons only on icon-only controls.
- **Pills** — `.pill .pill-{tone}` or `<StatusPill tone>`; 24px tall, never wrap.
- **Kbd** — `<Kbd>⌘</Kbd><Kbd>↵</Kbd>`; `modKey()` renders ⌘ on Apple, Ctrl elsewhere.
- **Cards / panels** — `.card-dark` (8px, inset hairline), `.panel-header` (40px pane headers).
- **Skeletons** — `<DarkSkeleton className="…">` sized exactly like the content it replaces.
- **Icon tiles** — `<IconBadge icon tone size>` for empty states and dialog headers.

## 3. Component architecture (student workspace)

```
app/student/labs/[id]/page.tsx        state + API wiring (run/test/lint/hint/submit, autosave, proctoring, shortcuts)
└─ WorkspaceShell                      h-dvh frame; ≥lg two fixed-fraction panes, <lg Editor|Results segmented control
   ├─ LabHeader                        56px: logo/back · breadcrumb (CS201 · Data Structures Lab › Lab 4) · due/saved
   │   ├─ TestStatusPill               reserved 10.5rem: "No test run yet" → shimmer "Running tests…" → "4/5 tests passing"
   │   ├─ ProctorChip                  shield + paste/tab counters, hover log
   │   └─ actions                      Run · Run tests (⌘↵) · Hint · Submit  (worksheet labs: Check answers · Hint · Submit)
   ├─ left: MultiTabEditor             Instructions + file tabs (main.py·Python, circuit.sim·Logic, data.ipynb·Notebook, Worksheet)
   │   ├─ InstructionsView | CodeEditor (Monaco, vlm-dark theme) | NotebookEditor | WorksheetView
   │   ├─ WorksheetView                (worksheet labs, components/workspace/worksheet/) no code: Apparatus (PendulumApparatus |
   │   │                               DcBench) → observation table (instrument columns read-only) → ScatterGraph (least-squares
   │   │                               line) → sections of steps with their own Check; NewtonFigure / SimpsonFigure draw from the
   │   │                               student's answers. Each step shows Correct / the check's guidance / nothing while blank
   │   ├─ CircuitWorkbench             (circuit.sim only, under the editor) toggles → LEDs, timing diagram, truth table, stale badge
   │   └─ status bar (32px)            "Linting via Gemma…" → "No issues" / "2 warnings" (click → jump to line) · runtime
   └─ right
       ├─ TestRunnerTerminal           pytest-style checklist; failures auto-expanded with Expected vs Actual diff
       └─ drawer tabs
           ├─ SocraticHintStepper      Hint 1 Conceptual Nudge → 2 Edge-Case Spotlight → 3 Logic Check, "Never gives raw spoilers"
           └─ RubricPanel              persistent score + criteria (survives reload via latest_submission)
overlays: ProctorGate · ConfirmSubmitDialog · RubricScorecardModal · FloatingNotice (errors, fullscreen) · proctor toast
exam-lockdown labs (lockdown_mode exam | seb; state machine in lib/useExamLockdown.ts):
          ExamGate (replaces ProctorGate) · SebRequiredGate · ExamLockOverlay (locked | resume | elsewhere) · ExamSubmittedBanner
```

### Exam lockdown (v1.2)
`useExamLockdown` derives one **phase** per tab and the page renders exactly one blocking screen for it:

| Phase | Screen | Notes |
|---|---|---|
| `gate` | `ExamGate` (on `StartGate`) — *Before you start* · rose *Your exam locks if you* · *During the exam*, "I have read these rules" tick enables **Start exam in fullscreen** | amber warning when another tab already holds the exam |
| `seb_required` | `SebRequiredGate` — 3 steps + **Open in Safe Exam Browser** (`sebs://…`) | `rejected` variant when SEB runs with the wrong config |
| `live` | the workspace | chip reads **Exam mode** / **SEB exam**; back links become plain text (leaving = lock) |
| `paused` | `BreakOverlay` (`components/workspace/Break.tsx`) — "On break", time left of the 10-minute break, Resume exam | header **Pause** → `BreakDialog`; polls every 3 s; time up → server locks |
| `locked` | `ExamLockOverlay` — reason, locked-at, violations, pulsing "Waiting for your mentor to unlock", tip to use Pause next time | polls every 3 s |
| `resume` | `ExamLockOverlay` — "Your mentor unlocked your exam" + **Resume exam** (re-enters fullscreen) | |
| `elsewhere` | `ExamLockOverlay` — "Exam open in another tab" | |
| `submitted` | `ExamSubmittedBanner` (bottom, emerald) + read-only editor, actions disabled | |

Worksheet checks are named by their description everywhere a student sees them (results panel, hints, instructions);
unanswered steps read **TO DO** in neutral grey rather than FAIL. Faculty review shows the readings table and step
answers with Correct / Wrong (`components/WorksheetAnswers.tsx`).

Blocking screens use `bg-canvas/95` + `backdrop-blur-md` at `z-[85]` (gates `z-[80]`) and offer no way to another
role: the faculty unlocks from their own session. Exam API errors (423 / 409 / 403) are mapped to these screens,
never to a toast.

Faculty side (light dashboard palette): **Live Lab Monitor** (`app/faculty/practicals/[id]/monitor`) — 4 count tiles,
amber "Indicators, not proof" note, locked rows tinted `bg-rose-50/60` and sorted first, Unlock (success) / Lock
(secondary → in-app reason dialog). **AlertsBell** (`components/AlertsBell.tsx`) sits left of the signed-in name for
faculty/HOD: rose count badge, dropdown of locked students linking to each monitor. **LockdownSettings** in
`PracticalForm`: Off / Strict exam mode / Safe Exam Browser radio cards (lockdown forces Proctored on), SEB Config Key
+ config URL with inline validation.

| Component | File | Key props |
|---|---|---|
| `WorkspaceShell` | `components/workspace/WorkspaceShell.tsx` | `header, left, right, overlays, mobilePane, onMobilePaneChange, resultsBadge` |
| `LabHeader` | `components/workspace/LabHeader.tsx` | `practical, result, running, hintLoading, save, proctored, proctorSummary, onRun, onRunTests, onAskTutor, onSubmit, exam?, actionsDisabled?, lockNav?` |
| `MultiTabEditor` | `components/workspace/MultiTabEditor.tsx` | `files, activeTab, onTabChange, lintByFile, lintLoading, onJump, engine, children` |
| `CircuitWorkbench` | `components/workspace/CircuitWorkbench.tsx` | `result, specs, stale, running, onSimulate` |
| `TestRunnerTerminal` | `components/workspace/TestRunnerTerminal.tsx` | `result, running, labType, expectedCount` (+ exported `parseExpectedActual`) |
| `SocraticHintStepper` | `components/workspace/SocraticHintStepper.tsx` | `hints, loading, error, onAsk, hasFailingTests, hintsUsedBefore` |
| `RubricScorecardModal` / `RubricPanel` / `ConfirmSubmitDialog` | `components/workspace/RubricScorecard.tsx` | `submission, loading, onClose, onViewBreakdown` / `submission` / `labTitle, hiddenTests, passing, onCancel, onConfirm` |
| `ProctorGate` / `ProctorChip` / `FloatingNotice` | `components/workspace/Proctoring.tsx` | `ProctorGate`: `proctoring, practical` · `ProctorChip`: `summary, exam?` |
| `StartGate` | `components/workspace/StartGate.tsx` | `heading, practical, modeLabel, sections, notices?, ackLabel, startLabel, starting, onStart, testId` — the shared pre-start screen: lab facts (course, title, due, mode), titled sections, an acknowledgement checkbox that enables Start. Rule text is built from the lab's own numbers (hidden tests, max score, `submission_limit`) |
| `ExamGate` / `SebRequiredGate` / `ExamLockOverlay` / `ExamSubmittedBanner` | `components/workspace/ExamLockdown.tsx` | phase-specific; see *Exam lockdown* |
| `AlertsBell` | `components/AlertsBell.tsx` | — (polls `/faculty/alerts` every 10 s) |

## 4. Rules
1. **Zero layout shift**: fixed 56px header, fixed pane fractions, fixed-height tab bars (40px) and status bars
   (32px / 44px), reserved width for live pills, notices are absolute overlays, skeletons match final geometry.
2. **One primary action per view** (brand). AI actions are violet. Destructive/failing states are rose.
3. **Mono for machine output** (tests, logs, scores, filenames); sans for prose.
4. **Never hardcode demo results** — every number (4/5, 9.5/10) comes from the API.
5. **Proctoring stays intact** in every refactor: gate before work, blocked clipboard/drop/context menu/devtools,
   telemetry from the editor, `flush()` before submit and before switching roles. Use the in-app
   `ConfirmSubmitDialog` — native `confirm()` makes browsers exit fullscreen, which used to be logged as a
   proctoring "fullscreen exit" on every honest submission.

## 5. 2-minute jury demo flow
1. Home → **Continue as Student** → Lab 4: Binary Search Trees → *Start proctored session*.
2. **Run Tests** (⌘↵) → header pill **4/5 tests passing**; `test_duplicate_keys` is auto-expanded with
   *expected size 3 / actual 6*.
3. Try ⌘V → blocked toast + proctor counter (integrity story).
4. **Hint** → stepper at *Hint 1 · Concept*.
5. Fix the equal-key branch → **Run tests** → 5/5 → **Submit** → confirm → score dialog
   (score ring, criteria bars) → *View breakdown*.
6. **Faculty** (signed in in a second browser): the new auto-graded submission + integrity badge. **HOD**: bottleneck
   `test_duplicate_keys`, integrity flags, conversational analytics.
7. Optional: EE210 Lab 3 Full Adder → circuit.sim → Run Tests → toggle inputs, watch LEDs + timing diagram.

Lab 4 is seeded in **strict exam mode**, so step 1 shows the exam gate (*Start exam in fullscreen*). To demo the
lockdown: switch tab → *Exam locked* → in the faculty browser: bell → Live Lab Monitor → **Unlock** →
student browser → **Resume exam** (see README "Demo the lockdown").

## 6. Minimal UI rules (house style)
The app should read as designed by a product designer: quiet, plain, consistent. These rules apply to every page;
the dark lab workspace keeps its tokens (section 1) but follows the same rules. Where this section conflicts with
sections 1–4, this section wins. The light primitives in `ui.tsx` already implement it.

**Icons.** No decorative icons: none in stat tiles, section or card headers, badges, chips, list items or next to
button text, and no icon tiles or arrows on links ("Open", not "Open lab →"). Keep an icon only when it *is* the
control or carries meaning the text doesn't: close (X), dropdown and expand chevrons, spinners, the alerts bell,
icon-only buttons with an `aria-label`.

**Text.** Short, plain, sentence-case headings. No subtitles that restate the obvious; one short line max for
explanations. No marketing or AI-ish phrasing ("AI-native", "Instant…", "seamless", "powered by", ✨, exclamation
marks, chains of em dashes). Model/provider info may stay as a short meta label where it exists ("Graded by
Gemini"). Prefer numbers to words ("4/5 tests"). Don't repeat what is already visible. Never show demo users' names
or emails in demo/role UI; use role names (Student / Faculty / HOD).

**Light pages.**
| Element | Recipe |
|---|---|
| Page | `bg-slate-50`, `PageContainer` (`max-w-7xl`), `space-y-6` between sections, `gap-4` grids |
| Card (`Card`) | `rounded-lg border border-slate-200 bg-white`, no shadow (`shadow-sm` at most), `p-5` |
| Card header (`CardHeader`) | `px-5 py-4`, title `text-sm font-semibold text-slate-900`, optional `text-xs text-slate-500` meta |
| Page title (`PageHeader`) | `text-xl sm:text-2xl font-semibold text-slate-900` |
| Body / meta | `text-sm text-slate-700` / `text-xs text-slate-500`; no uppercase tracking-wide labels |
| Stat tile (`StatTile`) | label `text-sm text-slate-500`, value `text-2xl font-semibold`, optional one-line meta; no icon; 3–4 tiles max |
| Badge (`Badge`, `ProgressChip`, `DueChip`, `StatusBadge`) | real status only, `rounded px-1.5 py-0.5 text-xs font-medium` on a light tint |
| Button (`Button`, `LinkButton`) | text only, `rounded-md`, `h-9` (md) / `h-8` (sm); primary solid indigo-600, secondary white + slate-300 border, ghost for tertiary |
| Input (`inputCls`, `Field`) | `rounded-md border-slate-300`, 36px tall, indigo focus ring; label `text-sm font-medium` |
| Table | header `text-xs font-medium text-slate-500` sentence case, rows `text-sm`, `divide-slate-100`, `py-3`+ rows |
| Empty state (`EmptyState`) | one short `text-sm text-slate-500` line, left-aligned in the card, no icon |

**Colour.** One accent, indigo-600, for primary actions, links and the active state. Status colours only for status:
emerald = pass/ok, amber = warning/due soon, rose = fail/locked/overdue. No gradients, glows, blur blobs or coloured
card backgrounds. Lab type (Coding / Circuit / Notebook) is plain meta text, not a chip; no file-name or language chips.

**Top nav.** Dark `bg-slate-950` bar, text wordmark "Virtual Lab Manager" (hidden on phones), plain text links
(active = white), alerts bell (faculty/HOD), signed-in name and **Log out** on the right. No role switcher anywhere:
a session is one person in one role.
