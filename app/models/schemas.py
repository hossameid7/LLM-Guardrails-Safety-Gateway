"""
Pydantic schemas for the Chat API.

Defines the request and response models used by the ``/api/v1/chat``
endpoint. All fields include descriptions for automatic OpenAPI docs.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat request from a client application.

    Attributes:
        prompt: The user's natural-language prompt.
        user_id: Optional identifier for per-user tracking / rate-limiting.
        temperature: LLM sampling temperature (lower = more deterministic).
    """

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="The user prompt to send through the guardrails pipeline.",
        examples=["What is the capital of France?"],
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user identifier for metrics and rate-limiting.",
        examples=["user-42"],
    )
    temperature: Optional[float] = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the LLM (0.0–2.0).",
    )


class ChatResponse(BaseModel):
    """Response returned to the client after the guardrails pipeline.

    Attributes:
        response: The LLM-generated (and unmasked) response text.
        sanitized_prompt: The prompt as it was sent to the LLM (after PII masking).
        cached: Whether the response was served from the semantic cache.
        latency_ms: End-to-end processing time in milliseconds.
        tokens_used: Total tokens consumed by the LLM (0 for cache hits).
        pii_masked: Whether PII masking was applied to the input.
        security_status: ``"clean"`` when no issues detected, or a description.
    """

    response: str = Field(
        ...,
        description="The final LLM response (with PII restored).",
    )
    sanitized_prompt: str = Field(
        ...,
        description="The prompt sent to the LLM after PII masking.",
    )
    cached: bool = Field(
        ...,
        description="True if the response was served from semantic cache.",
    )
    latency_ms: float = Field(
        ...,
        description="Total pipeline latency in milliseconds.",
    )
    tokens_used: int = Field(
        ...,
        description="Total LLM tokens consumed (0 for cache hits).",
    )
    pii_masked: bool = Field(
        ...,
        description="True if PII was detected and masked in the input.",
    )
    security_status: str = Field(
        default="clean",
        description="Security assessment: 'clean' or violation details.",
    )
