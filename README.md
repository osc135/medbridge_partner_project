# AI Health Coach

An AI-powered accountability partner that proactively engages patients through onboarding, goal-setting, and follow-up for home exercise programs (HEPs) — without crossing into clinical advice.

**Deployed:** [Railway URL here]

## Architecture

```
ai_health_coach/
  core/
    graph/         # LangGraph router + phase-specific subgraphs
    tools/         # Tool interfaces (set_goal, set_reminder, etc.)
    safety/        # Safety classifier (clinical/crisis detection)
    state/         # State schemas (PatientState, OnboardingState, etc.)
    llm.py         # LLM wrappers with safety checks
    persistence.py # SQLite state storage
  cli/             # CLI interface
  api/             # FastAPI backend
frontend/          # React (Vite) frontend
tests/             # Unit tests + LLM evals
```

The core logic is fully decoupled from the interface layer. The CLI, API, and frontend all consume the same `route_message()` entry point.

## Functional Requirements

### 1. Onboarding Conversation Flow
Multi-turn conversation: welcome (referencing assigned exercises) -> elicit goal (open-ended) -> extract structured goal (separate LLM call) -> confirm -> store via `set_goal` tool. Handles edge cases: no response (backoff), unrealistic goals (negotiation), refusal to commit (clinician alert), clinical questions mid-flow (safety redirect).

### 2. LangGraph Agent with Phase Routing
A parent router graph dispatches to phase-specific subgraphs:
- **PENDING** -> **ONBOARDING** (on login + consent)
- **ONBOARDING** -> **ACTIVE** (on goal confirmation)
- **ACTIVE** -> **RE_ENGAGING** (on first unanswered message)
- **RE_ENGAGING** -> **DORMANT** (after 3 unanswered)
- **DORMANT** -> **RE_ENGAGING** (when patient returns)

All transitions are deterministic application code — the LLM never decides phase changes.

### 3. Safety Classifier
Every generated message passes through a keyword-based three-way classifier before delivery:
- **Safe** -> deliver
- **Clinical** (pain, medication, diagnosis, etc.) -> hard redirect to care team, retry once with augmented prompt, fallback to safe generic message
- **Crisis** (self-harm, suicidal ideation) -> urgent clinician alert + crisis resources (988 Lifeline)

Designed with an upgrade path to swap in an LLM-based classifier without changing anything else.

### 4. Scheduled Follow-up
Day 2, 5, and 7 check-ins fired via trigger buttons. Each check-in references the patient's goal and uses tone appropriate to the milestone (Day 2: check-in, Day 5: encouragement, Day 7: celebration).

### 5. Disengagement Handling
Exponential backoff: 1 -> 2 -> 3 unanswered messages -> DORMANT. Clinician alert fires at the dormant threshold. When a dormant patient returns, warm re-engagement resets all counters and transitions back to ACTIVE.

### 6. Tool Calling
The LLM autonomously calls 5 tools based on context:
- `set_goal` — store confirmed exercise goal
- `set_reminder` — schedule follow-up check-ins
- `get_program_summary` — fetch assigned exercises
- `get_adherence_summary` — fetch adherence data (stubbed)
- `alert_clinician` — send disengagement or crisis alerts

Tools have real interfaces and invocation logic with least-privilege access per phase (e.g., `set_goal` only available during onboarding).

### 7. Consent Gate
First node in every graph invocation. No interaction occurs without both login and consent. Three outcomes: proceed, never consented (prompt login), revoked (acknowledge and pause). Phase is preserved on revocation — patients resume where they left off on re-consent.

## Running Locally

### Prerequisites
- Python 3.9+
- Node.js 18+
- OpenAI API key

### Setup

```bash
# Clone and enter the project
cd medbridge_partner_project

# Create Python virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Install and build frontend
cd frontend
npm install
npm run build
cd ..
```

### Running

**Option 1: Full-stack (API + frontend)**
```bash
# Start the server (serves both API and built frontend)
uvicorn ai_health_coach.api.routes:app --reload

# Open http://localhost:8000
# Clinician: use @healthcare.com email
# Patient: use any other email
```

**Option 2: Development (separate servers)**
```bash
# Terminal 1: API server
uvicorn ai_health_coach.api.routes:app --reload

# Terminal 2: Frontend dev server (hot reload)
cd frontend && npm run dev

# Open http://localhost:5173
```

**Option 3: CLI only**
```bash
# Create a patient
python -m ai_health_coach.cli.main new --patient-id P001 --name "Sarah" --exercises "Quad Sets:3:10,Heel Slides:2:15"

# Chat with them
python -m ai_health_coach.cli.main chat --patient-id P001

# Fire a check-in
python -m ai_health_coach.cli.main trigger --patient-id P001 --type day_2_checkin
```

## Testing

```bash
# Run unit tests (162 tests, no API calls)
pytest

# Run LLM evals (28 tests, hits OpenAI API)
pytest -m eval

# Run everything
pytest -m ""
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `LANGCHAIN_API_KEY` | No | LangSmith tracing (optional) |
| `LANGCHAIN_TRACING_V2` | No | Enable LangSmith tracing |
| `HEALTH_COACH_DB` | No | SQLite database path (default: `patients.db`) |

## Deployment

Configured for Railway deployment. The app runs as a single service — FastAPI serves both the API and the built React frontend.

```bash
# Railway will use nixpacks.toml for build configuration
# Set OPENAI_API_KEY in Railway environment variables
railway up
```
