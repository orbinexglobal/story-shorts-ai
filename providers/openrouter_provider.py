"""
OpenRouter text provider.

Reads OPENROUTER_API_KEY from the environment, plus optional
OPENROUTER_API_KEY_2 .. OPENROUTER_API_KEY_5 for extra free accounts.
Tries each model in order, rotating through every configured key for
that model before moving on (free-tier daily caps are per-account: 50
requests/day each, so 2 keys = 100/day, 3 = 150, etc.), so a cap on one
key can't waste the budget on the other models.

The free-tier model lineup changes often, so the provider re-checks
OpenRouter's live /api/v1/models list at startup (`auto_discover`) and
silently drops any configured slug OpenRouter no longer serves — dead
slugs only ever return 404. It also keeps process-wide cooldowns while a
run is in flight: a model that just failed hard (404/5xx) is skipped on
every remaining key and retry instead of wasting a request+wait on each,
and a model that has hit its per-key daily cap (429) on one key can still
be tried on the next key rather than re-hammering the capped one.
"""

from __future__ import annotations

import os
import threading
import time

import requests

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError, RateLimitError, TextProvider
from utils.rate_limit import is_rate_limit, throttle

logger = get_logger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Free-tier daily caps are per account (50 req/day each), so rotating
# multiple keys multiplies the daily budget: 2 keys = 100, 3 = 150, etc.
_KEY_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_2",
    "OPENROUTER_API_KEY_3",
    "OPENROUTER_API_KEY_4",
    "OPENROUTER_API_KEY_5",
)

# Cache discovered model lists for an hour so repeated provider instances
# within (and across nearby) runs don't re-poll the API every time.
_DISCOVERY_TTL_SECONDS = 3600

_cooldown_lock = threading.Lock()
_discovery_cache: tuple[float, list[str] | None] | None = None

# Models that failed with a non-429 error (404, 5xx, bad payload). These
# are permanently bad for this process, so never retry them at all.
_dead_models: set[str] = set()
# (key_index, model) pairs that returned 429. A daily cap on one key
# shouldn't stop the same model being tried on the next key.
_per_key_ratelimited: set[tuple[int, str]] = set()
# Models that have 429ed on every configured key: skip them everywhere.
_all_keys_ratelimited: set[str] = set()


def _load_api_keys() -> list[str]:
    """Return all configured OpenRouter keys, in order, de-duplicated."""
    keys: list[str] = []
    for env_name in _KEY_ENV_NAMES:
        value = os.environ.get(env_name)
        if value and value not in keys:
            keys.append(value)
    return keys


def _discover_free_models(timeout_seconds: int) -> list[str] | None:
    """
    Return the live list of `:free` model slugs, or None if discovery fails.

    A failed discovery is non-fatal: the caller falls back to the raw
    configured model list. The result is cached process-wide for an hour.
    """
    global _discovery_cache
    now = time.monotonic()
    with _cooldown_lock:
        if _discovery_cache is not None and now - _discovery_cache[0] < _DISCOVERY_TTL_SECONDS:
            return _discovery_cache[1]
    try:
        response = requests.get(_MODELS_URL, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()
        slugs = sorted(
            m["id"] for m in data.get("data", [])
            if str(m.get("id", "")).endswith(":free")
        )
        result: list[str] | None = slugs or None
    except Exception:  # noqa: BLE001 - discovery is a best-effort optimization
        logger.warning("OpenRouter model discovery failed; using configured slugs as-is.")
        result = None
    with _cooldown_lock:
        _discovery_cache = (now, result)
    return result


def _resolve_models(cfg: Config) -> list[str]:
    """
    Build the ordered model list to try.

    Config order wins. If live discovery succeeded, only slugs OpenRouter
    still serves are kept; if every configured slug turned out to be dead,
    fall back to the raw config list rather than failing the run outright.
    """
    openrouter_cfg = cfg.ai_providers.openrouter
    preferred = list(openrouter_cfg.preferred_models)
    fallback = [m for m in openrouter_cfg.fallback_models if m not in preferred]

    discovered_live: bool = False
    if openrouter_cfg.auto_discover:
        live = _discover_free_models(openrouter_cfg.discovery_timeout_seconds)
        if live is not None:
            discovered_live = True
            live_set = set(live)
            preferred = [m for m in preferred if m in live_set]
            fallback = [m for m in fallback if m in live_set]

    models = preferred + fallback
    if not models and discovered_live:
        # Discovery succeeded but found none of the configured slugs live.
        # Reintroducing them would only 404, so surface a clear error instead.
        raise ProviderError(
            "None of the configured OpenRouter :free models are currently live; "
            "update preferred_models/fallback_models in config.yaml."
        )
    if not models:
        # Discovery was skipped or failed: fall back to the raw config list.
        raw_preferred = list(openrouter_cfg.preferred_models)
        raw_fallback = [m for m in openrouter_cfg.fallback_models if m not in raw_preferred]
        models = raw_preferred + raw_fallback
    return models


class OpenRouterTextProvider(TextProvider):
    """Text generation via OpenRouter's OpenAI-compatible chat API."""

    name = "openrouter"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_keys = _load_api_keys()
        self._models = _resolve_models(cfg)
        if not self._models:
            raise ProviderError("No OpenRouter models configured.")
        logger.info(
            "OpenRouter will try %d model(s): %s",
            len(self._models), ", ".join(self._models),
        )

    @staticmethod
    def is_configured() -> bool:
        return bool(_load_api_keys())

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        if not self._api_keys:
            raise ProviderError("No OPENROUTER_API_KEY set")

        last_error: Exception | None = None
        for model in self._models:
            for key_idx, api_key in enumerate(self._api_keys):
                if not OpenRouterTextProvider._model_usable(key_idx, model):
                    continue
                try:
                    return self._call_model(api_key, model, prompt, max_tokens)
                except RateLimitError as exc:
                    # Free-tier 429s are per-account and per-model. A daily
                    # cap on one key shouldn't stop the next key trying it,
                    # and a cap on one model shouldn't stop the others.
                    # Only give up on a model once it has 429ed on every key.
                    OpenRouterTextProvider._mark_ratelimited(
                        key_idx, model, len(self._api_keys),
                    )
                    logger.warning(
                        "OpenRouter key..%s model %s rate-limited: %s", api_key[-4:], model, exc,
                    )
                    last_error = exc
                except Exception as exc:  # noqa: BLE001 - fall through to next key/model
                    # A 404/5xx means the slug is dead; don't retry it anywhere.
                    OpenRouterTextProvider._mark_dead(model)
                    logger.warning(
                        "OpenRouter key..%s model %s failed: %s", api_key[-4:], model, exc,
                    )
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

    @staticmethod
    def _model_usable(key_idx: int, model: str) -> bool:
        """True while a (key, model) pair is worth another API call."""
        with _cooldown_lock:
            return (
                model not in _dead_models
                and model not in _all_keys_ratelimited
                and (key_idx, model) not in _per_key_ratelimited
            )

    @staticmethod
    def _mark_dead(model: str) -> None:
        """Record a hard (non-429) failure so the model is skipped everywhere."""
        with _cooldown_lock:
            _dead_models.add(model)

    @staticmethod
    def _mark_ratelimited(key_idx: int, model: str, num_keys: int) -> None:
        """Remember a per-key 429; escalate to a global skip once it hits all keys."""
        with _cooldown_lock:
            _per_key_ratelimited.add((key_idx, model))
            if all((k, model) in _per_key_ratelimited for k in range(num_keys)):
                _all_keys_ratelimited.add(model)