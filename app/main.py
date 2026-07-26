"""
LLM Guardrails Gateway – FastAPI Application Entry Point.

Creates the FastAPI application, registers routers, configures CORS,
and exposes health-check endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.chat import router as chat_router
from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager.

    Logs configuration on startup and performs cleanup on shutdown.
    """
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("  🛡️  %s  starting up", settings.PROJECT_NAME)
    logger.info("  Model          : %s", settings.GROQ_MODEL)
    logger.info("  PII Masking    : %s", "ON" if settings.ENABLE_PII_MASKING else "OFF")
    logger.info(
        "  Injection Scan : %s",
        "ON" if settings.ENABLE_PROMPT_INJECTION_DETECTION else "OFF",
    )
    logger.info(
        "  Semantic Cache : %s",
        "ON" if settings.ENABLE_SEMANTIC_CACHE else "OFF",
    )
    logger.info("=" * 60)
    yield
    logger.info("🛡️  %s  shutting down", settings.PROJECT_NAME)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Enterprise gateway sitting between client applications and LLMs. "
        "Enforces PII anonymization, prompt-injection detection, semantic "
        "caching, and observability metrics."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS – allow the frontend playground to connect
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(chat_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    response_model=dict,
)
async def health_check() -> dict:
    """Return a simple health-check payload.

    Returns:
        ``{"status": "healthy", "service": "<project_name>"}``
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Serve the frontend playground at root
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the HTML playground UI."""
    return FileResponse("static/index.html")


# Mount static files (CSS, JS, etc.) if the directory exists
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except RuntimeError:
    logger.warning("No 'static' directory found – frontend will not be served.")
