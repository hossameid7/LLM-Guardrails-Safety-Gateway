"""
Chat endpoint – the core guardrails pipeline.

Request flow::

    Input → Injection Check → PII Masking → Semantic Cache Check
          → LLM Call (if cache miss) → Output Unmasking
          → Metrics Logging → Response

Each step is individually toggleable via feature flags in ``Settings``.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.security import verify_api_key_configured
from app.guardrails.pii_masker import PIIMasker
from app.guardrails.prompt_injection import PromptInjectionDetector
from app.models.schemas import ChatRequest, ChatResponse
from app.services.cache_service import SemanticCacheService
from app.services.llm_service import LLMService
from app.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# ---------------------------------------------------------------------------
# Singleton service instances (created once, reused across requests)
# ---------------------------------------------------------------------------
_injection_detector = PromptInjectionDetector()
_cache_service = SemanticCacheService()
_metrics_service = MetricsService()
_llm_service: LLMService | None = None


def _get_llm_service(settings: Settings) -> LLMService:
    """Lazily initialise the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService.from_settings(settings)
    return _llm_service


# ---------------------------------------------------------------------------
# POST /api/v1/chat
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a prompt through the guardrails pipeline",
    description=(
        "Pipes the user prompt through injection detection, PII masking, "
        "semantic caching, and the Groq LLM – then returns the response "
        "with full observability metadata."
    ),
)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(verify_api_key_configured),
) -> ChatResponse:
    """Execute the full guardrails pipeline for a single chat request.

    Args:
        request: Validated ``ChatRequest`` body.
        settings: Injected application settings (also validates API key).

    Returns:
        ``ChatResponse`` with the LLM answer and pipeline telemetry.
    """
    t_start = time.perf_counter()
    prompt = request.prompt
    pii_masked = False
    cached = False
    tokens_used = 0

    # ── Step 1: Prompt Injection Detection ────────────────────────
    if settings.ENABLE_PROMPT_INJECTION_DETECTION:
        logger.info("Running prompt-injection scan …")
        _injection_detector.scan(prompt)  # raises HTTPException(400) if bad
    security_status = "clean"

    # ── Step 2: PII Masking ───────────────────────────────────────
    masker = PIIMasker()
    sanitized_prompt = prompt
    if settings.ENABLE_PII_MASKING:
        sanitized_prompt, pii_masked = masker.mask(prompt)
        if pii_masked:
            logger.info(
                "PII masked: %d item(s) replaced", len(masker.masked_items),
            )

    # ── Step 3: Semantic Cache Lookup ─────────────────────────────
    response_text: str = ""
    if settings.ENABLE_SEMANTIC_CACHE:
        cache_result = _cache_service.lookup(sanitized_prompt)
        if cache_result is not None:
            response_text, _, tokens_used = cache_result
            cached = True
            logger.info("Serving response from semantic cache")

    # ── Step 4: LLM Call (on cache miss) ──────────────────────────
    if not cached:
        llm = _get_llm_service(settings)
        temperature = request.temperature if request.temperature is not None else 0.1
        response_text, tokens_used = await llm.chat(
            prompt=sanitized_prompt,
            temperature=temperature,
        )

        # Store in cache for future hits
        if settings.ENABLE_SEMANTIC_CACHE:
            _cache_service.store(sanitized_prompt, response_text, tokens_used)

    # ── Step 5: Output Unmasking ──────────────────────────────────
    if pii_masked:
        response_text = masker.unmask(response_text)

    # ── Step 6: Metrics Logging ───────────────────────────────────
    latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
    _metrics_service.record_request(
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        cached=cached,
        pii_masked=pii_masked,
        security_status=security_status,
        user_id=request.user_id,
    )

    logger.info(
        "Request completed: latency=%.2fms cached=%s tokens=%d",
        latency_ms,
        cached,
        tokens_used,
    )

    return ChatResponse(
        response=response_text,
        sanitized_prompt=sanitized_prompt,
        cached=cached,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        pii_masked=pii_masked,
        security_status=security_status,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/metrics  (bonus observability endpoint)
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    summary="Retrieve aggregated pipeline metrics",
    tags=["observability"],
)
async def metrics():
    """Return aggregated metrics for the guardrails pipeline."""
    return {
        "pipeline_metrics": _metrics_service.summary(),
        "cache_stats": _cache_service.stats,
    }
