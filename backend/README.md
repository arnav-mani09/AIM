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

## Deploying

Render deploys this folder (Root Directory `backend`) automatically when a push to `main` changes something under `backend/`; changes elsewhere in the repo don't trigger a backend deploy. Render runs the build command only, so apply new migrations yourself first: `PYTHONPATH=. .venv/bin/alembic upgrade head` (local and Render share the Supabase database). Check what's live with `curl https://aim-8tt1.onrender.com/health`, which returns the deployed commit.
