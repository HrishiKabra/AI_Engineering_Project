"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.pool import close_pool
from app.routes import ask, dashboard, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # resolve + export OPENAI_API_KEY early
    yield
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="F1 Rule & Penalty Interpreter",
        version="2.0.0",
        description="Agentic RAG over FIA regulations and steward decisions.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, tags=["ops"])
    app.include_router(dashboard.router, tags=["ops"])
    app.include_router(ask.router, tags=["agent"])
    return app


app = create_app()
