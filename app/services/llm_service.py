"""
LLM Service – asynchronous chat completions via Groq (OpenAI-compatible).

Uses ``langchain-openai``'s ``ChatOpenAI`` configured with Groq's base URL
and API key. All calls are made asynchronously via ``ainvoke``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Tuple

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class LLMService:
    """Asynchronous wrapper around Groq's LLM endpoint.

    Usage::

        service = LLMService.from_settings(settings)
        response_text, tokens = await service.chat(prompt, temperature=0.1)
    """

    _llm: ChatOpenAI = field(repr=False)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMService":
        """Construct an ``LLMService`` from application settings.

        Args:
            settings: Pydantic ``Settings`` instance with Groq credentials.

        Returns:
            A configured ``LLMService`` ready for async chat calls.
        """
        llm = ChatOpenAI(
            model=settings.GROQ_MODEL,
            openai_api_key=settings.GROQ_API_KEY,
            openai_api_base=settings.GROQ_BASE_URL,
            temperature=0.1,
            max_tokens=1024,
        )
        logger.info(
            "LLMService initialised (model=%s, base_url=%s)",
            settings.GROQ_MODEL,
            settings.GROQ_BASE_URL,
        )
        return cls(_llm=llm)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        prompt: str,
        temperature: float = 0.1,
    ) -> Tuple[str, int]:
        """Send a user prompt to the LLM and return the response.

        Args:
            prompt: The (possibly PII-masked) user prompt.
            temperature: Sampling temperature override.

        Returns:
            A tuple of ``(response_text, total_tokens_used)``.

        Raises:
            Exception: Propagated from the underlying HTTP call.
        """
        # Override temperature per-request if different from default
        self._llm.temperature = temperature

        message = HumanMessage(content=prompt)
        result = await self._llm.ainvoke([message])

        response_text: str = result.content  # type: ignore[assignment]
        tokens_used: int = 0

        # Extract token usage from response metadata when available
        if hasattr(result, "response_metadata"):
            usage = result.response_metadata.get("token_usage", {})
            tokens_used = usage.get("total_tokens", 0)

        logger.info("LLM response received (tokens=%d)", tokens_used)
        return response_text, tokens_used
