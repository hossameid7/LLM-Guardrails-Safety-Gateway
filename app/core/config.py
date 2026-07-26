"""
Application configuration loaded from environment variables via pydantic-settings.

All settings are centralized here and validated at startup. Missing required
fields (e.g., ``GROQ_API_KEY``) will prevent the application from launching.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the LLM Guardrails Gateway.

    Values are loaded from a ``.env`` file (if present) and can be overridden
    by real environment variables. Required fields that are missing will raise
    a ``ValidationError`` at import time.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Project Metadata ---
    PROJECT_NAME: str = "llm-guardrails-gateway"

    # --- Groq / LLM ---
    GROQ_API_KEY: str  # required – no default
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Feature Flags ---
    ENABLE_PII_MASKING: bool = True
    ENABLE_PROMPT_INJECTION_DETECTION: bool = True
    ENABLE_SEMANTIC_CACHE: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings.

    Using ``lru_cache`` ensures the ``.env`` file is read only once.
    """
    return Settings()  # type: ignore[call-arg]
