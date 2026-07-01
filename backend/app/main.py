"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import (
    ai,
    auth,
    daily_entries,
    documents,
    exercises,
    imports,
    pain_instances,
    records,
    sessions,
    stats,
    timer,
    weekly,
)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NerveTrack API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    for module in (
        auth,
        daily_entries,
        documents,
        exercises,
        pain_instances,
        records,
        sessions,
        timer,
        weekly,
        stats,
        imports,
        ai,
    ):
        app.include_router(module.router, prefix=API_PREFIX)

    return app


app = create_app()
