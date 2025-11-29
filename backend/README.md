# AIM Backend (FastAPI)

Python FastAPI stack for stats ingestion, JWT auth, and AI-model orchestration.

## Local setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The API expects a PostgreSQL database reachable with the DSN stored in `DATABASE_URL`.
