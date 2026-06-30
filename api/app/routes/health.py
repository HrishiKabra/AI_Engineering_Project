"""GET /health — DB connectivity, corpus size, configured models (no secrets)."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.db.pool import get_conn
from app.logging_ import corpus_status

router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    status = {"status": "ok", "chat_model": settings.chat_model, "embed_model": settings.embed_model}
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM chunks")
                status["chunks"] = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM documents")
                status["documents"] = cur.fetchone()[0]
            status["corpus"] = corpus_status(conn)
        status["db"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["status"] = "degraded"
        status["db"] = f"error: {type(e).__name__}"
    return status
