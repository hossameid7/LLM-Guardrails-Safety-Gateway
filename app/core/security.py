"""
Security utilities – API-key validation middleware and helpers.

Currently provides a lightweight dependency that validates the presence
of the Groq API key at startup. This module can be extended with
rate-limiting, JWT validation, or IP allow-listing as needed.
"""

from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings


async def verify_api_key_configured(
    settings: Settings = Depends(get_settings),
) -> Settings:
    """FastAPI dependency that ensures the Groq API key is set.

    Raises:
        HTTPException: 500 if the key is missing or empty.
    """
    if not settings.GROQ_API_KEY or settings.GROQ_API_KEY.startswith("gsk_your"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GROQ_API_KEY is not configured. Set it in your .env file.",
        )
    return settings
