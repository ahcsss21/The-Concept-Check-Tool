# The Concept Check Tool

A learning tool that identifies whether a learner truly understands a concept or has memorized a label. A learner names a concept, explains it in their own words, and the tool returns one thing: the single place where their explanation breaks, plus one follow-up question that exposes it.

## What it does

1. Learner picks a concept (Interfaces, Backend fundamentals, Data storage, etc.)
2. Learner submits a first free-form explanation
3. Tool identifies if any phrase looks memorized or lacks depth
4. If yes: shows the exact weak phrase and asks one targeted follow-up question
5. Learner submits a second attempt in response to the follow-up
6. A deterministic checklist evaluates the second attempt (rule-based)
7. A designated human reviewer marks the final verdict: gap closed or gap open
8. Learner sees only the final outcome, not the reviewer controls

## Architecture

```
Backend:   FastAPI + SQLAlchemy (Python)
Frontend:  React 18 + Vite (JavaScript)
Database:  SQLite (local) / PostgreSQL (production)
LLM:       Groq (llama-3.1-8b-instant) with OpenAI fallback
Hosting:   Render (backend web service + frontend static site)
```

## Deterministic vs Probabilistic boundary

| Deterministic (rule-based) | Probabilistic (LLM) |
|---|---|
| Auth token validation | Detect memorized/weak phrase in attempt 1 |
| Session ownership isolation | Generate follow-up question targeting that phrase |
| Reviewer-only permission gate | Decide NO_FOLLOWUP for strong answers |
| Weak-answer guardrail (word count + vagueness) | |
| Checklist evaluation (keyword rules) | |
| Final verdict persistence | |

Real bottleneck decision: human reviewer judgment (gap_closed), not the model.

## Project structure

```
/
├── app.py                  # FastAPI application, routes, LLM follow-up logic
├── models.py               # SQLAlchemy ORM models
├── database.py             # DB init, seed data, schema migration
├── run.py                  # Server entry point (uvicorn)
├── test_isolation.py       # Two-user isolation + FK linkage proof test
├── requirements.txt        # Python dependencies
├── render.yaml             # Render deployment blueprint
├── .env.example            # Environment variable template
└── frontend/
    ├── src/
    │   ├── App.jsx          # Root component, routing, auth state
    │   ├── api.js           # API client (all fetch calls)
    │   ├── main.jsx         # Entry point (HashRouter)
    │   └── pages/
    │       ├── Dashboard.jsx    # Topic picker (learner) / review queue (reviewer)
    │       ├── SessionPage.jsx  # Session flow: explanation, follow-up, outcome
    │       ├── Login.jsx
    │       └── SignUp.jsx
    ├── package.json
    └── vite.config.js
```

## Data model (key foreign keys)

```
learners
  └── sessions (learner_id FK)
        └── explanations (session_id FK)
              └── followup_questions (explanation_id FK)
              └── explanations.prompted_by_question_id -> followup_questions.question_id  ← CRITICAL FK
        └── gap_judgments (session_id FK)
        └── checklist_results (session_id FK, explanation_id FK)
```

The foreign key `explanations.prompted_by_question_id -> followup_questions.question_id` is the evidence path that connects the diagnosed gap to the learner's second-pass attempt.

## Setup (local development)

**Backend**

```bash
# Clone repo
git clone https://github.com/ahcsss21/The-Concept-Check-Tool.git
cd The-Concept-Check-Tool

# Create virtual env
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Fill in GROQ_API_KEY and REVIEWER_EMAILS

# Run backend
python run.py
```

Backend runs at: http://localhost:8000  
API docs at: http://localhost:8000/docs

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## Environment variables

| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | Groq API key for LLM follow-up generation | Yes |
| `GROQ_MODEL` | Groq model name | No (default: `llama-3.1-8b-instant`) |
| `OPENAI_API_KEY` | OpenAI fallback key | No |
| `FRONTEND_ORIGIN` | Deployed frontend URL (for CORS) | Production |
| `IS_PRODUCTION` | Set to `true` on Render for secure cookies | Production |
| `REVIEWER_EMAILS` | Comma-separated reviewer email list | Yes |
| `VITE_API_URL` | Backend base URL (used by frontend) | Yes |

## User roles

**Learner**
- Signs up and logs in
- Picks a concept topic
- Submits attempt 1 and attempt 2
- Sees deterministic checklist results
- Sees final outcome only: "Gap closed — you demonstrated understanding." or "Gap open — your explanation missed key reasoning or examples."

**Reviewer**
- Logs in with email listed in `REVIEWER_EMAILS`
- Sees all learner sessions in review queue on dashboard
- Opens a session and reviews attempt 1, follow-up question, attempt 2, checklist
- Marks gap closed or open (final human verdict)
- Learner cannot see or submit reviewer controls

## Deploy to Render

1. Backend: New Web Service from GitHub repo
   - Root directory: `.`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Env vars: `GROQ_API_KEY`, `GROQ_MODEL`, `REVIEWER_EMAILS`, `FRONTEND_ORIGIN`, `IS_PRODUCTION=true`

2. Frontend: New Static Site from GitHub repo
   - Root directory: `frontend`
   - Build command: `npm ci && npm run build`
   - Publish directory: `dist`
   - Env var: `VITE_API_URL=<backend URL>`

3. Set `FRONTEND_ORIGIN` in backend to the deployed frontend URL, then redeploy backend.

## Two-user isolation test

Run locally to verify session isolation and FK linkage:

```bash
python test_isolation.py
```

Expected output:
```
✓ ISOLATION WORKS: User B cannot read User A's session details
✓ ISOLATION WORKS: User B's session list does not include User A's session
✓ CRITICAL FK LINK: attempt 2 points back to the follow-up question.
```

## Concepts covered

1. Interfaces — How software components connect and communicate
2. Backend fundamentals — Why server-side systems exist behind the browser
3. Frontend vs Backend — How client-side and server-side roles differ
4. Data storage — Different ways to preserve and retrieve application data
5. Database fundamentals — Why systems need a database to manage structured state
6. Storage selection — How to choose different storage options based on requirements
