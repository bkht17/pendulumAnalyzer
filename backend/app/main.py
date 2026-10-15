from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException

from app.api import experiments, series, videos
from app.config import Settings, get_settings
from app.db import Database, prepare_sqlite_file
from app.services.jobs import TrackingQueue

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        prepare_sqlite_file(settings.database_path, related=(settings.videos_dir,))
        settings.videos_dir.mkdir(parents=True, exist_ok=True)
        database = Database(settings.database_url)
        database.create_all()
        queue = TrackingQueue(
            database.session_factory, settings.videos_dir, settings.tracking_workers
        )
        queue.recover_interrupted()
        app.state.settings = settings
        app.state.db = database
        app.state.queue = queue
        try:
            yield
        finally:
            queue.shutdown()
            database.engine.dispose()

    app = FastAPI(
        title="Секундомер против камеры",
        description="Измерение периода математического маятника вручную и по видео",
        version="0.1.0",
        lifespan=lifespan,
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(experiments.router)
    api.include_router(series.router)
    api.include_router(videos.router)

    # Неизвестные /api/* — честный JSON 404, а не index.html от фронтенда.
    @api.api_route(
        "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    def api_not_found(path: str) -> None:
        raise HTTPException(status_code=404, detail=f"Нет такого метода API: /api/{path}")

    app.include_router(api)

    # В продакшене одно приложение отдаёт и API, и собранный фронтенд (SPA: все пути → index.html).
    if (settings.frontend_dist / "index.html").exists():
        app.frontend("/", directory=settings.frontend_dist, fallback="index.html")
    else:
        log.info("Frontend build not found at %s — serving API only", settings.frontend_dist)

    return app


app = create_app()
