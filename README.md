# AIM

Basketball film analysis for high school coaching staffs: coaches upload game film, AIM processes it and drafts the box score.

## How it's deployed

| Piece | Where | Deploys |
| --- | --- | --- |
| Frontend (`aim-app/`, Next.js 16) | Vercel, https://aim-app-seven.vercel.app | Automatically on every push to `main` |
| Backend (`backend/`, FastAPI) | Render, https://aim-8tt1.onrender.com | On push to `main` (auto-deploy) |
| Film worker (`worker/film_worker.py`) | Modal app `aim-film` | `backend/.venv/bin/modal deploy worker/film_worker.py` |
| Database | Supabase Postgres | `cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head` |
| Film storage | Cloudflare R2 bucket `aim-film` | — |
| Errors and traces | Sentry org `aim-qn` (frontend and backend projects) | — |

Check what's live: `curl https://aim-8tt1.onrender.com/health` returns the backend's deployed commit.

Backend details: [backend/README.md](backend/README.md). Film upload and processing: [backend/docs/team-workspaces.md](backend/docs/team-workspaces.md).
