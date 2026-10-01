import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import auth, stats, ingestion, teams, clips, film, games, players
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.film_processing import FilmProcessingService

settings = get_settings()

FILM_POLL_SECONDS = 20


def _poll_film_jobs(stop: threading.Event) -> None:
    """Collect finished Modal film jobs even when no one has the page open."""
    while not stop.wait(FILM_POLL_SECONDS):
        db = SessionLocal()
        try:
            FilmProcessingService(db).refresh_pending()
        except Exception as exc:
            print(f"[FILM] Job poll failed: {exc}")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=_poll_film_jobs, args=(stop,), daemon=True, name="film-job-poller").start()
    yield
    stop.set()


app = FastAPI(title=settings.project_name, lifespan=lifespan)

allowed_origins = {
    settings.frontend_base_url,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origin for origin in allowed_origins if origin),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(stats.router, prefix=settings.api_v1_prefix)
app.include_router(ingestion.router, prefix=settings.api_v1_prefix)
app.include_router(teams.router, prefix=settings.api_v1_prefix)
app.include_router(clips.router, prefix=settings.api_v1_prefix)
app.include_router(film.router, prefix=settings.api_v1_prefix)
app.include_router(games.router, prefix=settings.api_v1_prefix)
app.include_router(players.router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health_check():
    # Render sets RENDER_GIT_COMMIT, so this shows which commit is live.
    return {"status": "ok", "commit": os.environ.get("RENDER_GIT_COMMIT", "local")[:7]}
