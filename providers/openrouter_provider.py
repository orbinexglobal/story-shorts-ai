"""
OpenRouter text provider.

Reads OPENROUTER_API_KEY from the environment, plus optional
OPENROUTER_API_KEY_2 .. OPENROUTER_API_KEY_5 for extra free accounts.
Tries each key in turn (free-tier daily caps are per-account: 50
requests/day each), and within each key tries each model in
`config.ai_providers.openrouter.preferred_models` in order — OpenRouter's
free-tier model lineup changes often, so nothing here hardcodes a
single model.
"""

from __future__ import annotations

import os

import requests

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError, RateLimitError, TextProvider
from utils.rate_limit import is_rate_limit, throttle

logger = get_logger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free-tier daily caps are per account (50 req/day each), so rotating
# multiple keys multiplies the daily budget: 2 keys = 100, 3 = 150, etc.
_KEY_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_2",
    "OPENROUTER_API_KEY_3",
    "OPENROUTER_API_KEY_4",
    "OPENROUTER_API_KEY_5",
)


def _load_api_keys() -> list[str]:
    """Return all configured OpenRouter keys, in order, de-duplicated."""
    keys: list[str] = []
    for env_name in _KEY_ENV_NAMES:
        value = os.environ.get(env_name)
        if value and value not in keys:
            keys.append(value)
    return keys


class OpenRouterTextProvider(TextProvider):
    """Text generation via OpenRouter's OpenAI-compatible chat API."""

    name = "openrouter"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_keys = _load_api_keys()
        self._models = cfg.ai_providers.openrouter.preferred_models

    @staticmethod
    def is_configured() -> bool:
        return bool(_load_api_keys())

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        if not self._api_keys:
            raise ProviderError("No OPENROUTER_API_KEY set")

        last_error: Exception | None = None
        for key in self._api_keys:
            for model in self._models:
                try:
                    return self._call_model(key, model, prompt, max_tokens)
                except RateLimitError as exc:
                    # Free-tier 429s are per-account and per-model. A daily
                    # cap on one key shouldn't stop us trying the next key,
                    # and a cap on one model shouldn't stop the other models.
                    # Only give up once every key × model has failed.
                    logger.warning("OpenRouter key..%s model %s rate-limited: %s", key[-4:], model, exc)
                    last_error = exc
                except Exception as exc:  # noqa: BLE001 - fall through to next key/model
                    logger.warning("OpenRouter key..%s model %s failed: %s", key[-4:], model, exc)
                    last_error = exc
        raise ProviderError(f"All OpenRouter keys/models failed. Last error: {last_error}")

    def _call_model(self, api_key: str, model: str, prompt: str, max_tokens: int) -> str:
        throttle("openrouter", self._cfg.rate_limits.rpm_for("openrouter"))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Optional but recommended by OpenRouter for attribution/rate-limit tiers.
            "X-Title": "StoryShorts AI",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.9,
        }
        response = requests.post(_API_URL, json=body, headers=headers, timeout=60)
        if is_rate_limit(response.status_code):
            raise RateLimitError(f"OpenRouter rate limit (HTTP 429) on {model}")
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected OpenRouter response shape: {data}") from exc
        if not content:
            raise ProviderError(f"OpenRouter returned empty content for {model}")
        return content
