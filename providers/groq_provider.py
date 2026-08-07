"""
Groq text provider.

Reads GROQ_API_KEY from the environment. Tries each model in
`config.ai_providers.groq.preferred_models` in order.
"""

from __future__ import annotations

import os

import requests

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError, RateLimitError, TextProvider
from utils.rate_limit import is_rate_limit, throttle

logger = get_logger(__name__)

_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqTextProvider(TextProvider):
    """Text generation via Groq's OpenAI-compatible chat API."""

    name = "groq"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_key = os.environ.get("GROQ_API_KEY")
        self._models = cfg.ai_providers.groq.preferred_models

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("GROQ_API_KEY"))

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        if not self._api_key:
            raise ProviderError("GROQ_API_KEY is not set")

        last_error: Exception | None = None
        for model in self._models:
            try:
                return self._call_model(model, prompt, max_tokens)
            except RateLimitError:
                raise  # same quota pool; let the chain back off
            except Exception as exc:  # noqa: BLE001 - fall through to next model
                logger.warning("Groq model %s failed: %s", model, exc)
                last_error = exc
        raise ProviderError(f"All Groq models failed. Last error: {last_error}")

    def _call_model(self, model: str, prompt: str, max_tokens: int) -> str:
        throttle("groq", self._cfg.rate_limits.rpm_for("groq"))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.9,
        }
        response = requests.post(_API_URL, json=body, headers=headers, timeout=60)
        if is_rate_limit(response.status_code):
            raise RateLimitError(f"Groq rate limit (HTTP 429) on {model}")
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected Groq response shape: {data}") from exc
        if not content:
            raise ProviderError(f"Groq returned empty content for {model}")
        return content
