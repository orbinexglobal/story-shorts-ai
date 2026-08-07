"""
OpenRouter text provider.

Reads OPENROUTER_API_KEY from the environment. Tries each model in
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


class OpenRouterTextProvider(TextProvider):
    """Text generation via OpenRouter's OpenAI-compatible chat API."""

    name = "openrouter"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_key = os.environ.get("OPENROUTER_API_KEY")
        self._models = cfg.ai_providers.openrouter.preferred_models

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("OPENROUTER_API_KEY"))

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        if not self._api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")

        last_error: Exception | None = None
        for model in self._models:
            try:
                return self._call_model(model, prompt, max_tokens)
            except RateLimitError:
                raise  # same quota pool; let the chain back off
            except Exception as exc:  # noqa: BLE001 - fall through to next model
                logger.warning("OpenRouter model %s failed: %s", model, exc)
                last_error = exc
        raise ProviderError(f"All OpenRouter models failed. Last error: {last_error}")

    def _call_model(self, model: str, prompt: str, max_tokens: int) -> str:
        throttle("openrouter", self._cfg.rate_limits.rpm_for("openrouter"))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
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
