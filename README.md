# Virtual Lab Manager — Team Algorithm Rangers

> **Startup Buildathon India 2026 — Final Prototype Submission**  
> **Live Demo URL:** [https://multimedia-let-columbus-visitor.trycloudflare.com](https://multimedia-let-columbus-visitor.trycloudflare.com)  
> **Walkthrough Video:** [`Virtual_Lab_Manager_Full_Walkthrough.mp4`](./Virtual_Lab_Manager_Full_Walkthrough.mp4)  
> **Final Presentation Deck:** [`Final_Prototype_Submission_Deck_Algorithm_Rangers.pptx`](./Final_Prototype_Submission_Deck_Algorithm_Rangers.pptx)

---

## 🎯 Executive Summary

**Virtual Lab Manager** is an AI-powered next-generation virtual lab operating system built for engineering institutions. It solves the massive physical lab bottleneck across 3,500+ colleges by providing a zero-setup browser IDE for code labs (`main.py`), interactive circuits (`circuit.sim`), engineering mathematics (Newton-Raphson & Simpson's rule), physics simulations (Simple Pendulum), and electrical benches (Ohm's Law).

Powered by **Gemini 2.5/1.5 & Gemma AI**, it features a real-time **Socratic AI Tutor** that guides students without spoon-feeding answers, automated rubric-based grading, an AI proctoring & academic integrity suite (detecting bulk pastes and AI-generated code patterns), and an executive **HOD analytics engine** to eliminate learning bottlenecks.

---

## 🌟 Key Capabilities by Role

| Role | Demo Account | Password | Core Features to Explore |
|---|---|---|---|
| **Student** | `aarav.sharma@demo.edu` | `demo1234` | Monaco code editor, test runner with live feedback, Socratic AI hint levels (no solution leak), interactive physics/math/circuits, exam mode lockdown. |
| **Faculty** | `meera.kulkarni@demo.edu` | `demo1234` | Auto-graded submissions with rubric breakdown, manual score override, student AI tutor conversation logs, AI practice practical generator, live lab exam monitor. |
| **HOD** | `rajesh.deshpande@demo.edu` | `demo1234` | Department bottleneck analytics, at-risk student identification, automated weekly briefing generator, AI natural language query assistant, compliance CSV export. |

*Quick Demo Tip: Use the one-click demo role buttons directly on the login page.*

---

## 📁 Repository Structure

```
.
├── Final_Prototype_Submission_Deck_Algorithm_Rangers.pptx   # Official 15-slide submission deck
├── Virtual_Lab_Manager_Full_Walkthrough.mp4                 # Full end-to-end demo video (<3 min)
├── Virtual_Lab_Manager/
│   ├── frontend/                                           # Next.js 16 + Tailwind 4 + Monaco Editor
│   │   ├── src/app/student/                                # Student workspace & interactive labs
│   │   ├── src/app/faculty/                                # Faculty grading & practical authoring
│   │   ├── src/app/hod/                                    # HOD analytics dashboard & insights
│   │   └── src/lib/api.ts                                  # API client with auto-proxy support
│   ├── backend/                                            # FastAPI high-performance backend
│   │   ├── app/ai/                                         # Gemini Socratic tutor & rubric grader
│   │   ├── app/api/                                        # REST endpoints (auth, labs, grading, etc.)
│   │   ├── app/db/                                         # Seed repository (PostgreSQL / In-memory)
│   │   └── app/execution/                                  # Sandboxed runner & test harnesses
│   ├── database/                                           # SQL schemas & migration scripts
│   └── docs/                                               # API contracts & architecture blueprints
└── README.md                                               # Main project documentation
```

---

## 🚀 Quick Start (Local Setup)

### 1. Backend (FastAPI + Python)
```bash
cd Virtual_Lab_Manager/backend

# Create virtual environment & install dependencies
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements-dev.txt

# Configure environment (copy example)
cp .env.example .env
# Set GEMINI_API_KEY=your_key_here (optional, falls back gracefully to rule-based engine)

# Start API server on port 8000
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (Next.js 16 + Tailwind CSS)
```bash
cd Virtual_Lab_Manager/frontend

# Install dependencies
npm install

# Run development server
npm run dev
# App will be accessible at http://localhost:3000
```

### 3. Run Backend Test Suite
```bash
cd Virtual_Lab_Manager/backend
pytest -q
```

---

## 🛡️ Proctoring & Academic Integrity Engine

Virtual Lab Manager includes active exam integrity protections:
- **Lockdown Exam Mode**: Enforces fullscreen focus, detects tab switches, developer console openings, and duplicate sessions. Mentor can unlock flagged sessions in real time via the **Live Lab Monitor**.
- **Behavioral & Code Integrity Analysis**: Tracks keystroke speed vs. character count, detecting suspicious bulk insertions and AI-generated code patterns with detailed probability scoring.
- **Safe Exam Browser (SEB) Support**: Native support for SEB Config Key verification for high-stakes institutional exams.

---

## 👥 Team Algorithm Rangers
- **Chintamani** — AI Architecture, Gemini Socratic Engine & System Integration
- **Tanishka** — Frontend Engineering, Monaco Workspaces & UI/UX
- **Vaishnavi** — Backend APIs, RBAC Security & Execution Sandbox
- **Aakash** — Institutional Datasets, Domain Modeling & Analytics

---

## 📄 License
This project is licensed under the terms described in [LICENSE](./LICENSE).
