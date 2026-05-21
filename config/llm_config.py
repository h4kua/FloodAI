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


def get_llm_config(*, require: list[str] | None = None) -> LLMConfig:
    """
    Load LLM API keys from environment variables.

    Args:
        require: Optional list of key names to validate at call time.
                 Accepted values: "anthropic".
                 Raises LLMConfigError for any missing key — use at startup.

    Returns:
        LLMConfig with anthropic_api_key (may be None when not required
        and not present in the environment).

    Raises:
        LLMConfigError: When a key listed in `require` is absent.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or None

    _log.debug(
        "llm_config loaded: anthropic_key=%s",
        "present" if anthropic_key else "absent",
    )

    cfg = LLMConfig(anthropic_api_key=anthropic_key)

    for name in (require or []):
        if name == "anthropic":
            cfg.require_anthropic()
        else:
            raise ValueError(f"Unknown key name in require list: {name!r}")

    return cfg
