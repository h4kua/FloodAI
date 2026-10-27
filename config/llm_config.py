"""
LLM API configuration loader.

Loads ANTHROPIC_API_KEY from environment variables.
Uses python-dotenv to read a local .env file when present.

Never logs or prints key values. Fails fast with a clear error when a
required key is missing so misconfiguration is caught at startup, not
mid-request.

Usage:
    from config.llm_config import get_llm_config
    cfg = get_llm_config()
    client = Anthropic(api_key=cfg.require_anthropic())
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv as _load_dotenv
    if os.getenv("FLOOD_LOAD_DOTENV", "1") == "1":
        _load_dotenv(override=False)
except ImportError:
    pass


class LLMConfigError(RuntimeError):
    """Raised when a required LLM API key is absent from the environment."""


@dataclass(frozen=True)
class LLMConfig:
    """Holds validated LLM API keys. Fields are never logged or serialised."""

    anthropic_api_key: str | None = field(default=None, repr=False)

    def require_anthropic(self) -> str:
        """Return the Anthropic key or raise LLMConfigError if missing."""
        if not self.anthropic_api_key:
            raise LLMConfigError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        return self.anthropic_api_key


def get_llm_config() -> LLMConfig:
    """
    Load LLM API keys from environment variables.

    Returns:
        LLMConfig with anthropic_api_key (may be None if not present in the
        environment) — call cfg.require_anthropic() to validate and raise.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or None

    _log.debug(
        "llm_config loaded: anthropic_key=%s",
        "present" if anthropic_key else "absent",
    )

    return LLMConfig(anthropic_api_key=anthropic_key)


# ─── Provider configuration (module-level constants) ───────────────────────────
# Groq is the primary backend (OpenAI-compatible, free, fast, Railway-friendly);
# Anthropic is kept as a fallback. Consumers may read these constants or call
# os.getenv directly — both resolve the same env vars.

# Anthropic (fallback)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# Groq (primary)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# llama-3.3-70b-versatile was withdrawn from Groq (model_not_found, 2026-10-27).
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_MODEL = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Active provider: "groq" | "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
