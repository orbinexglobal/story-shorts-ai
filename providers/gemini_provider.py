"""
Google Gemini text provider.

Reads GEMINI_API_KEY from the environment. Tries each model in
`config.ai_providers.gemini.preferred_models` in order, so the project
keeps working if a specific model is retired — nothing here hardcodes
a single model name.
"""

from __future__ import annotations

import os

import requests

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError, RateLimitError, TextProvider
from utils.rate_limit import is_rate_limit, throttle

logger = get_logger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTextProvider(TextProvider):
    """Text generation via Gemini's generateContent endpoint."""

    name = "gemini"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_key = os.environ.get("GEMINI_API_KEY")
        self._models = cfg.ai_providers.gemini.preferred_models

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        if not self._api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

        last_error: Exception | None = None
        for model in self._models:
            try:
                return self._call_model(model, prompt, max_tokens)
            except RateLimitError:
                raise  # same quota pool for every model; let the chain back off
            except Exception as exc:  # noqa: BLE001 - fall through to next model
                logger.warning("Gemini model %s failed: %s", model, exc)
                last_error = exc
        raise ProviderError(f"All Gemini models failed. Last error: {last_error}")

    def _call_model(self, model: str, prompt: str, max_tokens: int) -> str:
        throttle("gemini", self._cfg.rate_limits.rpm_for("gemini"))
        url = f"{_API_BASE}/{model}:generateContent?key={self._api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9},
        }
        response = requests.post(url, json=body, timeout=60)
        if is_rate_limit(response.status_code):
            raise RateLimitError(f"Gemini rate limit (HTTP 429) on {model}")
        response.raise_for_status()
        data = response.json()
        try:
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected Gemini response shape: {data}") from exc
        if not content:
            raise ProviderError(f"Gemini returned empty content for {model}")
        return content
