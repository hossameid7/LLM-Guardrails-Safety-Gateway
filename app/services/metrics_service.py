"""
Observability / Metrics Service.

Tracks per-request and aggregate metrics in-memory:
- Request count, latency percentiles
- Token usage totals
- Cache hit/miss ratio
- PII masking events
- Security violation counts

Designed to be extended with Prometheus or OpenTelemetry exporters.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class _RequestRecord:
    """Single request telemetry record."""

    timestamp: float
    latency_ms: float
    tokens_used: int
    cached: bool
    pii_masked: bool
    security_status: str
    user_id: str | None = None


@dataclass
class MetricsService:
    """In-memory metrics aggregator.

    Usage::

        metrics = MetricsService()
        metrics.record_request(latency_ms=120.5, tokens_used=350, ...)
        summary = metrics.summary()
    """

    _records: List[_RequestRecord] = field(default_factory=list, init=False, repr=False)
    _violations: int = field(default=0, init=False)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_request(
        self,
        *,
        latency_ms: float,
        tokens_used: int,
        cached: bool,
        pii_masked: bool,
        security_status: str = "clean",
        user_id: str | None = None,
    ) -> None:
        """Log metrics for a single completed request.

        Args:
            latency_ms: End-to-end latency in milliseconds.
            tokens_used: Total tokens consumed by the LLM (0 for cache hits).
            cached: Whether the response was served from cache.
            pii_masked: Whether PII masking was applied.
            security_status: ``"clean"`` or description of violation.
            user_id: Optional user identifier.
        """
        record = _RequestRecord(
            timestamp=time.time(),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            cached=cached,
            pii_masked=pii_masked,
            security_status=security_status,
            user_id=user_id,
        )
        self._records.append(record)
        logger.debug(
            "Recorded metrics: latency=%.2fms tokens=%d cached=%s pii=%s",
            latency_ms,
            tokens_used,
            cached,
            pii_masked,
        )

    def record_violation(self) -> None:
        """Increment the security violation counter."""
        self._violations += 1

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return an aggregate summary of all recorded metrics.

        Returns:
            Dictionary containing total counts, averages, and breakdowns.
        """
        total = len(self._records)
        if total == 0:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0.0,
                "cache_hit_rate": 0.0,
                "pii_masking_rate": 0.0,
                "security_violations": self._violations,
            }

        total_tokens = sum(r.tokens_used for r in self._records)
        avg_latency = sum(r.latency_ms for r in self._records) / total
        cache_hits = sum(1 for r in self._records if r.cached)
        pii_events = sum(1 for r in self._records if r.pii_masked)

        latencies = sorted(r.latency_ms for r in self._records)
        p50 = latencies[int(total * 0.50)] if total else 0.0
        p95 = latencies[min(int(total * 0.95), total - 1)] if total else 0.0
        p99 = latencies[min(int(total * 0.99), total - 1)] if total else 0.0

        return {
            "total_requests": total,
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "cache_hit_rate": round(cache_hits / total, 4),
            "pii_masking_rate": round(pii_events / total, 4),
            "security_violations": self._violations,
        }
