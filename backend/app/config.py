"""Runtime configuration read from environment variables. No secrets are hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # load backend/.env when present (optional dependency)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    max_chars: int = field(default_factory=lambda: _int("MAX_CONTENT_CHARS", 100_000))
    # LLM: none | openai | anthropic. "openai" covers any OpenAI-compatible endpoint
    # (OpenAI, Groq, OpenRouter, Together, local Ollama/LM Studio) via LLM_BASE_URL.
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "none").lower())
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "45")))
    # Source retrieval: none | brave
    search_provider: str = field(default_factory=lambda: os.getenv("SEARCH_PROVIDER", "none").lower())
    search_api_key: str = field(default_factory=lambda: os.getenv("SEARCH_API_KEY", ""))
    max_claims_to_verify: int = field(default_factory=lambda: _int("MAX_CLAIMS_TO_VERIFY", 5))
    # URL extraction
    fetch_timeout: float = field(default_factory=lambda: float(os.getenv("FETCH_TIMEOUT_SECONDS", "10")))
    fetch_max_bytes: int = field(default_factory=lambda: _int("FETCH_MAX_BYTES", 3_000_000))
    allow_private_urls: bool = field(
        default_factory=lambda: os.getenv("ALLOW_PRIVATE_URLS", "false").lower() == "true"
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        ]
    )


settings = Settings()


def reload_settings() -> Settings:
    """Re-read env vars (used by tests)."""
    global settings
    new = Settings()
    settings.__dict__.update(new.__dict__)
    return settings
