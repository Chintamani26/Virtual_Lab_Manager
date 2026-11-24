# Virtual Lab Manager (VLM) — Comprehensive Product Understanding & UI/UX Design Specification
> **Document Status:** Complete Single-Source-of-Truth Architecture & UI/UX Blueprint  
> **Role Context:** Senior Product Manager, Lead Product Designer, UI/UX Architect, UX Researcher, and Design Systems Engineer  
> **Target Framework:** Next.js 16 (App Router) + React 19 + Tailwind CSS v4 + Monaco Editor  
> **Backend Architecture:** FastAPI (Python 3.12 ASGI) + Gemini 3.5 & Gemma AI  
> **Design Thesis:** "Developer-First Academic SaaS" — Dual-mode visual architecture uniting high-density, zero-latency dark IDE workspaces for students with crisp, high-clarity executive light workspaces for faculty and administration.

---

## 1. Product Overview
**Virtual Lab Manager (VLM)** is an institutional-grade, multi-disciplinary virtual laboratory operating system built for universities, polytechnics, and engineering colleges. It eliminates physical laboratory hardware bottlenecks, manual grading backlogs, and academic dishonesty by delivering zero-setup, in-browser execution across four fundamental engineering paradigms:
1. **Software & Algorithm Engineering:** Real-time Python 3 sandbox with Monaco editor, standard library execution, and automated pytest-style assertion suites.
2. **Digital Electronics & Logic Design:** Interactive logic circuit simulation (`circuit.sim`) with signal propagation, timing diagrams, interactive toggle switches, live LED indicators, and automated truth-table verification.
3. **Data Science & Scientific Computing:** Interactive Jupyter-compatible notebooks (`data.ipynb`) supporting stepwise cell execution, stdout/stderr streams, and data tabular visualizations.
4. **Engineering Mathematics & Virtual Physics/Electrical Benches:** Structured interactive worksheet labs (`answers.json`) featuring step-by-step numerical checks (Newton-Raphson, Simpson's Rule), apparatus data collection (Simple Pendulum, DC Bench), and dynamic least-squares scatter-plot regression.

Underpinning these workspaces is a specialized, multi-tiered AI engine powered by **Gemini 3.5 & Gemma**:
- **Socratic Lab Tutor:** A multi-turn, anti-spoiler cognitive assistant that provides progressive hints (conceptual nudge → edge-case focus → algorithmic logic) without ever leaking code fixes.
- **Automated Rubric Grader:** Objective, criterion-by-criterion evaluation that pairs automated test coverage with qualitative code inspection and actionable student feedback.
- **Behavioral & Code Academic Integrity Suite:** Continuous proctoring tracking typing cadence, burst velocities, clipboard events, tab switching, and AI code generation hallmarks.
- **Institutional Intelligence Engine:** Executive analytics for faculty and Heads of Department (HOD) that turn raw lab telemetry into early pacing alerts, deterministic student risk scores, and department-wide learning friction heatmaps.

---

## 2. Problem Statement
Technical higher education globally, and specifically across India's 3,500+ engineering institutions, suffers from acute systemic laboratory challenges:
1. **Hardware & Infrastructure Deficits:** Physical computer and electronics laboratories are capital-intensive. Hardware (breadboards, oscilloscopes, IC chips) is frequently burned or broken, and access is restricted to 2 hours per week per student.
2. **Environment Configuration Fatigue:** Up to 40% of lab time is wasted resolving local compiler incompatibilities, environment variables, driver installations, and OS quirks rather than understanding algorithms.
3. **The LLM "Copy-Paste" Crisis:** Unrestricted access to commercial generative AI leads students to paste raw code solutions without comprehension, causing widespread plagiarism and completely breaking traditional homework grading models.
4. **Crushing Faculty Evaluation Workload:** Course instructors manually inspect thousands of physical and digital lab journals each semester. Grading turnaround takes 2 to 4 weeks, eliminating timely formative feedback.
5. **Institutional Blindspots:** Department heads have no real-time data regarding student drop-off, conceptual bottlenecks, or accreditation compliance until end-semester examination failures occur.

---

## 3. Product Purpose
The core mission of Virtual Lab Manager is to democratize, standardize, and accelerate technical education by providing:
- **Instant Equalized Access:** Zero-setup browser access to high-performance engineering workspaces on any client device (from mobile phones to entry-level laptops).
- **Enforced Socratic Mastery:** Pedagogical AI guardrails ensuring students engage in genuine cognitive problem solving rather than passive answer retrieval.
- **Instant Objective Assessment:** Real-time test-case validation combined with deterministic, transparent rubric grading.
- **Academic Governance & Exam Security:** Built-in exam lockdown mode, proctoring telemetry, and Safe Exam Browser (SEB) support for high-stakes institutional examinations.
- **Actionable Curriculum Telemetry:** Automated conversion of granular test execution failures into department-level curriculum interventions and accreditation-ready audit trails.

---

## 4. Target Audience
VLM is designed for three distinct institutional user tiers within STEM and engineering colleges:
1. **Undergraduate & Postgraduate Students:** Enrolled in Computer Science, Electrical Engineering, Electronics, Information Technology, and Applied Mathematics courses.
2. **Course Instructors, Professors, & Lab Assistants:** Responsible for creating practicals, monitoring live lab sessions, evaluating subjective code quality, and conducting viva voce examinations.
3. **Academic Administrators (Heads of Department, Deans, Academic Directors):** Responsible for faculty workload allocation, student retention, syllabus pacing, and accreditation (NBA / NAAC) compliance.

---

## 5. User Personas

### Persona A: Aarav Sharma — 2nd Year CSE Student
- **Profile:** 19 years old, enrolled in *CS201: Data Structures Lab*. Uses a modest 8GB RAM laptop with erratic internet connectivity.
- **Frustrations:** Gets stuck on subtle edge cases (e.g., duplicate keys in Binary Search Trees) and suffers debugging paralysis. Afraid of asking professors basic questions. When using ChatGPT, he gets penalized because professors recognize generic AI code.
- **Goals:** Understand *why* his logic fails; receive instant feedback on unit tests; know his grades immediately before final submission; retain working progress across devices.
- **VLM Solution:** Dark-themed Monaco IDE with instant pytest test runner, failure diff overlays, and progressive Socratic hints that guide without spoiling.

### Persona B: Prof. Meera Kulkarni — Associate Professor & Lab In-Charge
- **Profile:** 38 years old, manages 3 lab sections comprising 180+ enrolled students. Evaluates 10 mandatory practicals per semester per student (1,800+ total submissions).
- **Frustrations:** Spends entire weekends grading repetitive code files. Spends lab hours policing tab switching and mobile phone usage instead of teaching. Has no objective proof of code sharing or AI generation.
- **Goals:** Automated grading against transparent criteria; instant visibility into who is copying vs. who is genuinely struggling; one-click lockdown exam invigilation with easy unlock controls.
- **VLM Solution:** Automated rubric grading with manual override, Live Lab Monitor with lock-reason auditing, and automated teaching/viva material generators.

### Persona C: Dr. Rajesh Deshpande — Head of Department (HOD)
- **Profile:** 52 years old, oversees 24 faculty members, 800+ students, and 18 departmental lab courses. Prepares periodic compliance dossiers for NBA/NAAC accreditation.
- **Frustrations:** Learns about student academic failures only after semester results are published; lacks visibility into whether faculty are keeping up with grading; manually collects spreadsheets from faculty for compliance audits.
- **Goals:** High-level department overview; automated identification of at-risk students before they fail; clear curriculum difficulty heatmaps; one-click export of compliance reports.
- **VLM Solution:** Executive HOD dashboard, conversational "Ask AI" analytics assistant, weekly department briefings, and single-click compliance CSV export.

---

## 6. Core Use Cases (P0 — Essential Foundation)

### UC-101: Interactive Code Lab Execution & Real-Time Unit Testing
- **Target User:** Student
- **User Problem:** Inability to know if code works correctly before submission.
- **Starting Point:** Student Dashboard → Course Page → Select Practical.
- **Workflow:**
  1. Student reviews lab objectives, constraints, and starter files.
  2. Edits `main.py` in Monaco editor.
  3. Clicks **Run Tests (`⌘↵` / `Ctrl+Enter`)**.
  4. Sandbox executes code against pytest test suite in <800ms.
  5. UI updates header status pill (`4/5 tests passing`) and displays terminal breakdown with expected vs. actual diffs.
- **Expected Output:** Color-coded test report, clear error traceback, and instant status pill update.
- **Key Dependencies:** Sandbox Runner, Monaco Editor, Pytest Harness.
- **Priority:** P0

### UC-102: Multi-Turn Socratic AI Tutoring (Anti-Spoiler Guardrails)
- **Target User:** Student
- **User Problem:** Debugging paralysis when unit tests fail.
- **Starting Point:** Lab Workspace → Right Drawer → "Ask Tutor" or "Hint".
- **Workflow:**
  1. System checks current test failure context and current code snapshot.
  2. Level 1 Hint delivers a conceptual nudge explaining the underlying CS theory.
  3. If student remains stuck, Level 2 identifies the divergence branch/function.
  4. Level 3 outlines algorithmic steps in plain English (strictly zero code blocks).
  5. If student passes all visible tests, Tutor poses a Concept-Check verification question.
- **Expected Output:** Multi-turn dialogue with zero copy-pasteable answers and strict prompt injection guards.
- **Key Dependencies:** Gemini Socratic Prompt Engine, Tutor Guard, Anti-Canary Leak Detection.
- **Priority:** P0

### UC-103: Automated Rubric Evaluation & Scorecard Generation
- **Target User:** Student & Faculty
- **User Problem:** Subjective grading, slow feedback cycles, lack of transparency.
- **Starting Point:** Lab Workspace Header → **Submit** Button.
- **Workflow:**
  1. Student confirms submission via dialog.
  2. Backend runs full test suite (including hidden edge-case tests).
  3. AI Evaluator grades submission against instructor's rubric criteria (0–10 scale in 0.5 steps).
  4. Academic integrity engine computes AI style score, keystroke ratio, and copy-paste flags.
  5. Scorecard modal displays final score, criteria breakdown, and actionable feedback.
- **Expected Output:** Persistent `SubmissionRecord` with permanent timestamp and rubric breakdown.
- **Key Dependencies:** Rubric Grader Engine, Hidden Test Runner.
- **Priority:** P0

### UC-104: Practical Authoring with AI Test Generation
- **Target User:** Faculty
- **User Problem:** Creating robust unit tests, starter templates, and rubrics takes hours.
- **Starting Point:** Faculty Dashboard → **+ New Practical**.
- **Workflow:**
  1. Faculty specifies title, course, lab type (coding/circuit/notebook/worksheet), and deadline.
  2. Enters problem topic and clicks **Generate Tests**.
  3. AI produces 6–8 Python assertions including 2 hidden edge-case tests.
  4. Faculty tests solution against authoring sandbox using **Validate**.
  5. Configures lockdown mode and clicks **Publish**.
- **Expected Output:** Published practical live for all enrolled students.
- **Key Dependencies:** AI Testgen Service, Authoring Sandbox.
- **Priority:** P0

### UC-105: Live Lab Exam Lockdown & Remote Invigilation
- **Target User:** Faculty & Student
- **User Problem:** Digital cheating, tab switching, and unauthorized collaboration during exams.
- **Starting Point:** Student opens lockdown practical; Faculty opens Live Lab Monitor.
- **Workflow:**
  1. Student encounters fullscreen **Exam Gate**. Must acknowledge exam rules.
  2. Fullscreen enforced; devtools, clipboard paste, tab blur, and multi-window access are blocked.
  3. If student attempts violation (e.g., switches window), workspace locks immediately with reason logged.
  4. Faculty sees row turn rose (`Locked: Tab blur`) on **Live Lab Monitor**.
  5. Student requests mentor assistance; Faculty clicks **Unlock** with required audit note.
  6. Student clicks **Resume Exam** to re-enter fullscreen workspace.
- **Expected Output:** Real-time synchronized exam state with zero client-side bypasses.
- **Key Dependencies:** Exam State Machine, WebSocket / Polling Heartbeat, Proctor Telemetry.
- **Priority:** P0

---

## 7. Secondary Use Cases (P1 — Value & Efficiency Enhancers)

### UC-201: Manual Faculty Grade & Feedback Override
- **Target User:** Faculty
- **User Problem:** Automated scoring misses unique student design elegance or requires discretionary adjustments.
- **Starting Point:** Faculty Dashboard → Submissions Queue → Select Submission.
- **Workflow:** Faculty reviews test assertion results, AI rubric remarks, and student code; inputs manual score override and comment; saves review.
- **Priority:** P1

### UC-202: Academic Integrity Audit Inspection
- **Target User:** Faculty & HOD
- **User Problem:** Identifying whether high scores were achieved via external AI generation or paste dumps.
- **Starting Point:** Submission Review → Integrity Badge.
- **Workflow:** Displays typing burst velocity (characters/sec), ratio of typed vs. inserted code, focus lost events, and AI styling hallmarks.
- **Priority:** P1

### UC-203: Digital Logic Circuit Simulation & Timing Analysis
- **Target User:** Student (EE / ECE)
- **User Problem:** Breadboard hardware wiring is tedious and hard to debug.
- **Starting Point:** Lab Workspace with `circuit.sim`.
- **Workflow:** Student edits logic netlist; clicks **Simulate**; interacts with live input switches; observes real-time LED states and clock timing diagrams.
- **Priority:** P1

### UC-204: Worksheet Apparatus Simulation & Regression Plotting
- **Target User:** Student (Physics / Maths)
- **User Problem:** Physical lab equipment errors and manual graph plotting mistakes.
- **Starting Point:** Worksheet Practical (Pendulum / DC Bench).
- **Workflow:** Student operates virtual instrument apparatus; readings populate observation table; student inputs step calculations; UI computes least-squares regression line.
- **Priority:** P1

---

## 8. Advanced Use Cases (P2 — Differentiation & Institutional Scale)

### UC-301: HOD Conversational Department Analytics ("Ask AI")
- **Target User:** HOD
- **User Problem:** Extracting cross-cohort insights requires complex database queries.
- **Starting Point:** HOD Dashboard → **Ask** Tab.
- **Workflow:** HOD asks natural language questions (e.g., "Which practical had the highest failure rate this week?"); Gemini Analyst answers using structured department telemetry snapshots with highlights and tables.
- **Priority:** P2

### UC-302: Institutional Pacing & Curriculum Bottleneck Heatmap
- **Target User:** HOD & Faculty
- **User Problem:** Identifying syllabus failure points only after end-semester exams.
- **Starting Point:** Faculty/HOD Dashboard → **Intelligence** Tab.
- **Workflow:** System aggregates test execution failures across all runs; visualizes top failing assertions, fail rates, and affected student counts.
- **Priority:** P2

### UC-303: Deterministic At-Risk Student Identification
- **Target User:** HOD & Faculty
- **User Problem:** Students slipping behind unnoticed in large cohorts.
- **Starting Point:** Intelligence Tab → **At-Risk Students**.
- **Workflow:** Deterministic scoring engine calculates risk (low completion + overdue labs + low scores + stagnant attempts); surfaces actionable intervention recommendations.
- **Priority:** P2

---

## 9. User Journey Maps

### 9.1 Student Journey: Completing an Algorithm Practical
```
[Login Screen] ──(1-Click Demo / Email)──> [Student Dashboard]
                                                    │
                                         (Select Due Practical)
                                                    ▼
                                           [Exam / Start Gate]
                                                    │
                                         (Acknowledge Rules)
                                                    ▼
                                           [IDE Lab Workspace]
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              ▼                                           ▼
                       [Monaco Editor]                             [Pytest Terminal]
                     (Write Implementation)                       (Run Tests: ⌘+Enter)
                              │                                           │
                              └─────────────────────┬─────────────────────┘
                                                    ▼
                                            [Test Failure?]
                                             ├── Yes ──> [Socratic Tutor Drawer] (Hints 1-3)
                                             └── No  ──> [Concept Check Question]
                                                                  │
                                                          (Click Submit)
                                                                  ▼
                                                      [Confirm Submit Modal]
                                                                  ▼
                                                       [Rubric Scorecard Modal]
```

### 9.2 Faculty Journey: Authoring, Supervision & Evaluation
```
[Faculty Dashboard] ──> [+ New Practical] ──> [AI Test Case Generator] ──> [Validate in Sandbox]
         │                                                                          │
         │                                                                   (Click Publish)
         │                                                                          ▼
         ├──> [Live Lab Monitor] <──(Real-Time Heartbeat)── [Active Student Exam Sessions]
         │         │
         │   (Detect Violation) ──> [Student Locked] ──> [Mentor Review & Unlock]
         │
         └──> [Submissions Tab] ──> [Select Student] ──> [Inspect Integrity & Rubric] ──> [Save Review]
```

---

## 10. Information Architecture
The platform enforces role-based separation:
- A user session represents exactly **one person in one role** (no role-switching dropdowns inside active views).
- Navigating between views adheres to zero-layout-shift principles with consistent top navigation bars.

```
Virtual Lab Manager Root
├── / (Public Authentication Gateway)
│   ├── User Login Form (Email + Password)
│   └── 1-Click Role Access Cards (Student / Faculty / HOD)
│
├── /student (Student Portal)
│   ├── Dashboard (Assigned Labs, Course Progress Cards, To-Do / Completed Views)
│   ├── /student/courses/[id] (Single Course Lab Roster)
│   └── /student/labs/[id] (Full-Screen Distraction-Free IDE Workspace)
│       ├── Fixed Header (Breadcrumb, Status Pill, Proctor Chip, Timer, Action CTAs)
│       ├── Left Split Pane (Instructions, Monaco Code Editor, Notebook, Worksheet)
│       └── Right Split Pane (Test Runner Terminal, Socratic Hint Stepper, Rubric Panel)
│
├── /faculty (Faculty Portal)
│   ├── Dashboard (Tabs: Practicals, Submissions, Where Students Struggle, Intelligence, Courses)
│   ├── /faculty/practicals/new (Practical Creation Wizard & AI Test Generator)
│   ├── /faculty/practicals/[id]/edit (Metadata, Files, Tests & Lockdown Settings)
│   ├── /faculty/practicals/[id]/submissions (Cohort Submission Table)
│   ├── /faculty/practicals/[id]/monitor (Live Lab Exam Monitor & Real-Time Invigilation)
│   ├── /faculty/submissions/[id] (Detailed Submission Review, Diff Viewer & Proctor Timeline)
│   └── /faculty/teaching (AI Teaching Material & Viva Question Generator)
│
└── /hod (Department Executive Portal)
    └── Dashboard (Tabs: Overview KPIs, AI Insights, Intelligence, Courses & Faculty, Compliance, Ask AI)
```

---

## 11. Sitemap
```
/
├── /student
│   ├── /student/courses/[id]
│   └── /student/labs/[id]
├── /faculty
│   ├── /faculty/practicals/new
│   ├── /faculty/practicals/[id]/edit
│   ├── /faculty/practicals/[id]/submissions
│   ├── /faculty/practicals/[id]/monitor
│   ├── /faculty/submissions/[id]
│   └── /faculty/teaching
└── /hod
```

---

## 12. Navigation Structure
- **Persistent Header:** 56px (`h-14`) global header with dark slate background (`bg-slate-950`).
- **Student Navigation:** Contextual breadcrumbs (`CS201 › Lab 4: Binary Search Trees`). When exam lockdown is active, navigation links are disabled to prevent accidental abandonment.
- **Faculty & HOD Navigation:** Underline tab bar (`UnderlineTabs`) with accessible keyboard arrow navigation, active indicator underline, and count badges.
- **Global Actions:** Right-aligned Alerts Bell (polls `/faculty/alerts` every 10s with live badge count), User Name display, and Sign Out button.

---

## 13. Recommended Design Direction: "Developer-First Academic SaaS"

### Visual Philosophy
1. **The Student Workspace is Dark (`#0a0b0f` canvas):** Inspired by **Linear**, **Vercel**, and **Replit**. Code is the hero element. Low eye strain during 2-hour lab sessions.
2. **The Faculty & HOD Dashboards are Light (`#f8fafc` slate-50):** Inspired by **Stripe Dashboard** and **Raycast for Teams**. High scanning velocity, clear tabular data, zero visual clutter.
3. **No Decorative Fluff:** No floating 3D icons, no unnecessary gradient blobs, no marketing slogans. Every pixel serves an educational or operational purpose.

---

## 14. Brand Identity
- **Name:** Virtual Lab Manager (VLM)
- **Wordmark:** Clean sans-serif wordmark paired with an indigo dot accent.
- **Tone:** Objective, technical, academic, precise, encouraging.
- **Copywriting Style:** Sentence-case headings. Numerical precision (`4/5 tests passed`, never "Almost there!").

---

## 15. Color System

### 15.1 Dark Palette (Student IDE Workspace)
- Canvas Background: `#0a0b0f` (`bg-canvas`)
- Surface Level 1 (Panes, Gutter): `#0f1117` (`bg-surface-1`)
- Surface Level 2 (Cards, Active Tabs): `#151821` (`bg-surface-2`)
- Surface Level 3 (Inputs, Controls): `#1c202b` (`bg-surface-3`)
- Hairline Border: `rgba(255, 255, 255, 0.06)` (`border-line`)
- Active Control Border: `rgba(255, 255, 255, 0.12)` (`border-line-strong`)
- Primary Text: `#e6e8ee` (`text-fg`)
- Muted Metadata Text: `#9aa3b2` (`text-fg-muted`)
- Faint Text & Line Numbers: `#6b7280` (`text-fg-faint`)
- Brand Accent: `#6366f1` (`indigo-500`)

### 15.2 Light Palette (Faculty & HOD Dashboards)
- Page Background: `#f8fafc` (`slate-50`)
- Card Surface: `#ffffff` (`white`)
- Structural Border: `#e2e8f0` (`slate-200`)
- Primary Text: `#0f172a` (`slate-900`)
- Secondary Text: `#475569` (`slate-600`)
- Muted Table Headers: `#64748b` (`slate-500`)

### 15.3 Semantic Colors
- **Pass / Success:** Emerald (`#10b981`) — dark: `bg-emerald-500/10 text-emerald-300 ring-emerald-500/20` | light: `bg-emerald-50 text-emerald-700 ring-emerald-600/20`
- **Warning / Pacing Gap:** Amber (`#f59e0b`) — dark: `bg-amber-500/10 text-amber-300 ring-amber-500/20` | light: `bg-amber-50 text-amber-700 ring-amber-600/20`
- **Error / Lockdown / High Risk:** Rose (`#f43f5e`) — dark: `bg-rose-500/10 text-rose-300 ring-rose-500/20` | light: `bg-rose-50 text-rose-700 ring-rose-600/20`
- **AI / Socratic Nudge:** Purple (`#8b5cf6`) — dark: `bg-purple-500/10 text-purple-300 ring-purple-500/20` | light: `bg-purple-50 text-purple-700 ring-purple-600/20`
- **Info / Neutral:** Slate (`#64748b`) — `bg-slate-100 text-slate-700 ring-slate-200`

---

## 16. Typography System
- **UI Font:** `Inter`, `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- **Code & Numeric Font:** `JetBrains Mono`, `monospace` (ligatures enabled)

### Typography Scale
- Display Score: `30px` (`1.875rem`), Line Height: `36px`, Weight: `700`, `font-mono tabular-nums`
- Page Title: `24px` (`1.5rem`), Line Height: `32px`, Weight: `600`, `font-sans`
- Section Title: `18px` (`1.125rem`), Line Height: `28px`, Weight: `600`, `font-sans`
- Body Regular: `14px` (`0.875rem`), Line Height: `20px`, Weight: `400`, `font-sans`
- Body Medium: `14px` (`0.875rem`), Line Height: `20px`, Weight: `500`, `font-sans`
- Table Header / Meta: `12px` (`0.75rem`), Line Height: `16px`, Weight: `500`, `font-sans`
- Code / Terminal: `13px` (`0.8125rem`), Line Height: `18px`, Weight: `400`, `font-mono`

---

## 17. Spacing and Layout System
- **Base Grid:** `4px` baseline unit.
- **Scale:**
  - Micro: `4px` (`0.25rem`), `8px` (`0.5rem`)
  - Component Padding: `12px` (`0.75rem`), `16px` (`1rem`), `20px` (`1.25rem`)
  - Section Spacing: `24px` (`1.5rem`), `32px` (`2rem`)
- **Max Width:** `max-w-7xl` (`1280px`) centered on dashboards.
- **Viewport Lock:** Student IDE locked to exactly `100dvh` with zero window scrollbar.

---

## 18. Component Design System Specification

### 18.1 Buttons
- **Primary:** `h-9 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-md shadow-sm transition-colors`
- **Secondary:** `h-9 px-3.5 py-2 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium border border-slate-300 rounded-md transition-colors`
- **Ghost:** `h-9 px-3.5 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 text-sm font-medium rounded-md`
- **Destructive:** `h-9 px-3.5 py-2 bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium rounded-md`

### 18.2 Cards & Panels
- Dashboard Card: `rounded-lg border border-slate-200 bg-white shadow-sm p-5`
- Dark IDE Pane: `rounded-none border-r border-line bg-surface-1`

### 18.3 Tables
- Container: `overflow-x-auto border border-slate-200 rounded-lg`
- Header: `border-b border-slate-100 bg-slate-50/75 px-3 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider`
- Data Row: `border-b border-slate-100 hover:bg-slate-50/60 py-3 text-sm`
- Numeric Cells: `text-right font-mono tabular-nums`

### 18.4 Badges & Status Pills
- Compact format: `inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset`

---

## 19. Page-by-Page UI Specifications

### 19.1 Landing & Login (`/`)
- Purpose: Secure role-based entry point with 1-click evaluation access.
- Target User: All roles.
- Sections: Product banner, 1-Click Demo role access cards, Email/Password login form.
- Primary CTA: "Sign In to Portal".
- Responsive: Card centers on mobile; full background gradient coverage.

### 19.2 Student Dashboard (`/student`)
- Purpose: Overview of enrolled courses, lab deadlines, and completed grades.
- Target User: Student.
- Sections: Course tab filter, Stat tiles (completed/assigned, average score, hints used), Course cards grid, All practicals split view (To Do vs. Completed).
- Primary CTA: "Start Lab" on next pending practical.

### 19.3 Student IDE Workspace (`/student/labs/[id]`)
- Purpose: Distraction-free, zero-setup execution and learning environment.
- Target User: Student.
- Layout:
  - Header (56px): Breadcrumb, Test status pill, Proctor chip, Timer/Pause, Run Code, Run Tests, Ask Tutor, Submit.
  - Left Pane (55%): Tab bar (Instructions, `main.py`, etc.), Monaco editor, Gemma status bar.
  - Right Pane (45%): Test runner terminal (pytest output), Drawer tab (Socratic Tutor vs. Rubric Panel).

### 19.4 Faculty Dashboard (`/faculty`)
- Purpose: Assignment administration, grading queue, cohort intelligence.
- Target User: Faculty.
- Sections: Page header with "New Practical" CTA, Stat tiles, Underline tabs (`Practicals`, `Submissions`, `Where Students Struggle`, `Intelligence`, `Courses`), Submissions review table.

### 19.5 Live Lab Exam Monitor (`/faculty/practicals/[id]/monitor`)
- Purpose: Real-time exam supervision and invigilation.
- Target User: Faculty.
- Sections: Summary count tiles (Online, Active, Locked, Submitted), Live student roster table with lock status, violations count, and mentor **Unlock** action button.

### 19.6 HOD Dashboard (`/hod`)
- Purpose: Department governance, accreditation compliance, faculty workload distribution.
- Target User: HOD.
- Sections: Header with "Export Compliance CSV", Department KPI tiles, Underline tabs (`Overview`, `AI Insights`, `Intelligence`, `Courses & Faculty`, `Compliance`, `Ask AI`), 14-day activity chart, score distribution histogram.

---

## 20. Text-Based Wireframes

### 20.1 Authentication & 1-Click Access (`/`)
```
+-----------------------------------------------------------------------+
|                             [VLM Mark]                                |
|                        Virtual Lab Manager                            |
|     Interactive Engineering Labs, Socratic AI & Rubric Evaluation     |
+-----------------------------------------------------------------------+
|  +-----------------------------------------------------------------+  |
|  | ONE-CLICK DEMO ACCESS                                           |  |
|  | [🎓 Student ] Aarav Sharma   · BST Lab, Hints & Submit    [Enter]|  |
|  | [🧑‍🏫 Faculty ] Meera Kulkarni · Grading, Monitor & Tests    [Enter]|  |
|  | [🏛️ HOD     ] Dr. Deshpande  · Department Intelligence    [Enter]|  |
|  +-----------------------------------------------------------------+  |
|  | OR SIGN IN WITH INSTITUTIONAL CREDENTIALS                       |  |
|  | Email:    [ student@college.edu                               ] |  |
|  | Password: [ ••••••••••••••••                                  ] |  |
|  |           [        Sign In to Portal        ]                   |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
```

### 20.2 Student IDE Lab Workspace (`/student/labs/[id]`)
```
+-----------------------------------------------------------------------+
| ← CS201 › Lab 4: BST   [● 4/5 Passing] [Shield: Proctored] [Submit]   |
| Actions: [Run Code] [Run Tests ⌘↵] [Ask Tutor]                        |
+------------------------------------+----------------------------------+
| [Instructions] [main.py*]          | TEST RUNNER (pytest)             |
| 1  class BSTNode:                  | ✓ test_empty_tree_init     PASSED|
| 2      def __init__(self, key):    | ✓ test_single_insert       PASSED|
| 3          self.key = key          | ✗ test_duplicate_keys      FAILED|
| 4          self.left = None        |   AssertionError: expected size 3|
| 5          self.right = None       |   Actual: 4                      |
| 6                                  |----------------------------------|
| 7      def insert(self, key):      | SOCRATIC AI TUTOR    [Rubric]    |
| 8          if key < self.key:      | Tutor: What should happen to a   |
| 9              ...                 | node's size when inserting an    |
|                                    | identical duplicate key?         |
| [Ln 8, Col 14] [Gemma: Clean]      | [ Type question to tutor... ]    |
+------------------------------------+----------------------------------+
```

### 20.3 Faculty Command Center (`/faculty`)
```
+-----------------------------------------------------------------------+
| VLM  Virtual Lab Manager       [Alerts (2)]   Prof. Kulkarni    [Out] |
+-----------------------------------------------------------------------+
| Faculty Dashboard  [Faculty Badge]              [+ New Practical]     |
| Manage practicals, review submissions & analyze cohort intelligence   |
|                                                                       |
| [Practicals (6)] [Submissions (48)] [Intelligence] [Courses (2)]      |
|                                                                       |
| +-------------------+  +-------------------+  +--------------------+  |
| | Active Practicals |  | Pending Review    |  | Average Turnaround |  |
| | 6 Published       |  | 8 Submissions     |  | 1.2 Days           |  |
| +-------------------+  +-------------------+  +--------------------+  |
|                                                                       |
| INTELLIGENCE & COHORT FRICTION                                        |
| +-------------------------------------------------------------------+ |
| | AT-RISK STUDENTS IN YOUR COURSES                                  | |
| | • Rohit Verma (Roll 104) | Risk: 85 (High) | 2 Overdue labs       | |
| | • Sneha Patil (Roll 112) | Risk: 65 (High) | Low test avg (38%)   | |
| +-------------------------------------------------------------------+ |
| | TOP BOTTLENECKS (DIFFICULTY HEATMAP)                              | |
| | • test_duplicate_keys    | CS201 Lab 4 | 72% Fail Rate | 34 Hints | |
| | • test_reversal_pointers | CS201 Lab 2 | 58% Fail Rate | 19 Hints | |
| +-------------------------------------------------------------------+ |
+-----------------------------------------------------------------------+
```

### 20.4 Live Lab Exam Monitor (`/faculty/practicals/[id]/monitor`)
```
+-----------------------------------------------------------------------+
| ← CS201 › Lab 4 Exam Monitor                   [Lockdown: Strict Exam]|
+-----------------------------------------------------------------------+
| Total: 48  |  Active: 44  |  Locked: 2  |  Submitted: 2               |
+-----------------------------------------------------------------------+
| Student Name     | Roll No | Status | Violations | Time Away | Action |
+------------------+---------+--------+------------+-----------+--------+
| Rohit Verma      | CS21B04 | LOCKED | 3 Paste    | 42s       |[Unlock]|
| Ananya Sen       | CS21B19 | ACTIVE | 0          | 0s        | [Lock] |
| Dev Patel        | CS21B28 | LOCKED | 1 Tab Blur | 15s       |[Unlock]|
+------------------+---------+--------+------------+-----------+--------+
```

### 20.5 HOD Executive Suite (`/hod`)
```
+-----------------------------------------------------------------------+
| VLM  Virtual Lab Manager          [Export Compliance CSV]  Dr. Deshpande|
+-----------------------------------------------------------------------+
| Department of Computer Science & Engineering                          |
| 24 Faculty · 812 Students · 18 Lab Courses                            |
|                                                                       |
| [Overview] [AI Insights] [Intelligence] [Courses] [Compliance] [Ask]  |
|                                                                       |
| +-------------------+  +-------------------+  +--------------------+  |
| | Overall Completion|  | Dept Average Score|  | At-Risk Students   |  |
| | 78.4%             |  | 8.2 / 10.0        |  | 14 Students        |  |
| +-------------------+  +-------------------+  +--------------------+  |
|                                                                       |
| FACULTY WORKLOAD DISTRIBUTION                                         |
| +-------------------------------------------------------------------+ |
| | Faculty Name      | Courses | Practicals | Pending | Avg Turnaround| |
| | Prof. M. Kulkarni | 2       | 6          | 8       | 1.2d          | |
| | Prof. S. Sharma   | 3       | 9          | 24 [!]  | 3.8d (High)   | |
| +-------------------------------------------------------------------+ |
+-----------------------------------------------------------------------+
```

---

## 21. Interaction and Micro-interaction Guidelines
- **Keyboard Shortcuts:**
  - `⌘↵` / `Ctrl+Enter`: Immediately triggers **Run Tests**.
  - `⌘S` / `Ctrl+S`: Manually forces instant draft synchronization to server.
  - `Esc`: Dismisses modals, scorecard overlays, or popovers.
- **Autosave Behavior:** Debounced by 2000ms. Status transitions seamlessly between `Unsaved` → `Saving…` → `Saved at HH:MM`.
- **Assertion Failure Diffs:** Failing unit tests automatically expand in the terminal to show a structured side-by-side diff between expected and actual output.
- **Proctoring Toast Warnings:** Blocked paste attempts or devtools triggers spawn a subtle non-blocking rose toast: `Paste blocked by proctoring policy`.

---

## 22. Responsive Design Guidelines
- **Desktop (≥1024px):** Fixed dual-pane split view (55% Editor, 45% Output).
- **Tablet (768px–1023px):** Editor and terminal stack vertically or support horizontal collapsible drawers.
- **Mobile (<768px):** Segmented control toggle at top switches between `[Editor]` and `[Results/Terminal]` full-screen panes.

---

## 23. Accessibility Guidelines (WCAG 2.2 AA)
- **Contrast Ratios:** Text against dark canvas `#0a0b0f` achieves `14.2:1` (exceeds AAA). Dashboard light text achieves `12.6:1`.
- **Keyboard Navigation:** Full focus trapping in modals (`ConfirmSubmitDialog`, `RubricScorecardModal`). Visible 2px indigo outline on active inputs.
- **Screen Reader Announcements:** Test runner results and execution errors use `aria-live="polite"` regions.
- **Reduced Motion:** All shimmers and pulse effects strictly respect `@media (prefers-reduced-motion: reduce)`.

---

## 24. Empty, Loading, Error, and Success States
- **Loading State:** Shimmering skeletons matching the exact geometry of cards or table rows (`PageSkeleton`, `DarkSkeleton`). Zero layout shift.
- **Empty State:** Clean, left-aligned card text (`EmptyState`) with a descriptive message and an optional single action button.
- **Error State:** Clear inline callouts (`InlineError`, `ErrorState`) detailing root cause and a retry button.
- **Success State:** Subdued emerald badge or brief toast confirmation; permanent records rendered on scorecards.

---

## 25. Product Differentiation Opportunities
1. **Socratic Guardrail Architecture:** Unlike commercial LLM wrappers that output complete code, VLM guarantees multi-tiered pedagogical guidance without code leakage.
2. **True Multi-Discipline Scope:** Houses software engineering, logic circuits, data science notebooks, and virtual instrument worksheets in a single system.
3. **Deterministic Institutional Intelligence:** Risk scores are 100% explainable and formulaic (no hallucinated AI warnings), giving academic chairs actionable justification for student interventions.
4. **Zero-Setup Client Execution:** Complete freedom from local environment configuration friction, leveling the playing field for students with entry-level laptops.
5. **Integrated Exam Proctoring with SEB Support:** High-stakes exam capabilities built right into the platform, avoiding expensive third-party invigilation software licenses.

---

## 26. Technical Implementation Recommendations
- **Frontend Stack:** Next.js 16 (App Router), React 19, Tailwind CSS v4, Monaco Editor (`@monaco-editor/react`), Lucide React.
- **Backend Stack:** FastAPI (Python 3.12 ASGI), Pydantic v2 domain schemas, pytest engine.
- **State Management:** URL-driven state for tabs/filters; lightweight local hooks (`useApi`, `useExamLockdown`, `useProctoring`) for real-time telemetry.
- **Database:** Unified repository architecture supporting PostgreSQL (Supabase/AlloyDB/Cloud SQL) and Firestore.

---

## 27. Existing Components to Reuse

| Component | Path | Purpose |
|:---|:---|:---|
| `Card`, `CardHeader` | `frontend/src/components/ui.tsx` | Standard light container frames |
| `StatTile` | `frontend/src/components/ui.tsx` | Standard KPI metric tiles |
| `UnderlineTabs` | `frontend/src/components/ui.tsx` | Accessible horizontal section tabs |
| `PerformanceCard` | `frontend/src/components/intelligence.tsx` | Student score distribution histograms |
| `WorkloadCard` | `frontend/src/components/intelligence.tsx` | Faculty grading velocity and queue stats |
| `CompletionCard` | `frontend/src/components/intelligence.tsx` | Cohort pacing gap tracking |
| `AtRiskCard` | `frontend/src/components/intelligence.tsx` | Deterministic student risk table |
| `HeatmapCard` | `frontend/src/components/intelligence.tsx` | Test assertion failure heatmap |
| `TestRunnerTerminal`| `frontend/src/components/workspace/TestRunnerTerminal.tsx` | Pytest assertion output pane |
| `MultiTabEditor` | `frontend/src/components/workspace/MultiTabEditor.tsx` | Monaco editor tab manager |
| `TutorChat` | `frontend/src/components/workspace/TutorChat.tsx` | Multi-turn Socratic conversation pane |

---

## 28. Components to Create
1. **`SplitPaneResizeHandle.tsx`:** Draggable divider enabling users to customize the 55%/45% split between Monaco Editor and Test Terminal.
2. **`SubmissionHistoryDrawer.tsx`:** Side-by-side historical attempt viewer comparing student code revisions across multiple submissions.
3. **`VivaVoicePanel.tsx`:** Interactive oral examination interface generating viva questions and recording instructor marks during practical vivas.
4. **`AccreditationExportModal.tsx`:** Specialized modal allowing HODs to select custom semester dates and generate formatted PDF accreditation dossiers.

---

## 29. Implementation Roadmap

### Phase 1: Core Foundation & Stability (Current State — Complete)
- [x] Monaco code execution with Pytest assertions.
- [x] Socratic AI Tutor with prompt injection guards.
- [x] Live Lab Exam Lockdown and Proctoring engine.
- [x] Full Student & Faculty Intelligence Module (5 features for Faculty & HOD).

### Phase 2: Ergonomic Polish & Student Experience
- [ ] Add draggable split-pane resizing to student IDE workspace.
- [ ] Implement submission revision history diff viewer.
- [ ] Add dark/light mode toggle for Faculty/HOD dashboards.

### Phase 3: Enterprise Accreditation & Mobile Invigilation
- [ ] Automated PDF accreditation dossier generation for NBA / NAAC compliance committee audits.
- [ ] Faculty mobile companion PWA for real-time exam lockdown unlock approvals from a smartphone.

---

## 30. Assumptions and Open Questions

### Confirmed Functionality
- Deterministic risk scoring produces reliable, explainable student risk flags without AI hallucinations.
- Socratic AI tutor strictly forbids code block output >1 line.
- Exam lockdown strictly enforces single-session fullscreen operation.

### Documented Assumptions
- Student workstations support modern evergreen browsers with WebAssembly and Web Worker support.
- Institutional grading adheres to a 0–10 scale compatible with the rubric engine.

### Open Questions for Institutional Scale
- *LMS Grade Sync:* Will institutions require LTI 1.3 integration (Canvas/Moodle/Blackboard) for automated roster and grade syncing?
- *Sandbox Deployment:* Will production environments utilize local subprocess runners or multi-node containerized Judge0 clusters for heavy student concurrency?
