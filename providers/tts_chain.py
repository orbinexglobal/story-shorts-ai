"""
TTS provider fallback chain.

Tries the configured primary TTS provider, then the fallback, per
`config.tts`. The offline provider is intentionally NOT part of this
chain — it's only ever selected explicitly by main.py under --offline.
"""

from __future__ import annotations

import time

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import ProviderError, RateLimitError, TTSProvider, TTSResult
from providers.edge_tts_provider import EdgeTTSProvider
from providers.gemini_tts_provider import GeminiTTSProvider

logger = get_logger(__name__)

_PROVIDER_CLASSES: dict[str, type] = {
    "gemini": GeminiTTSProvider,
    "edge_tts": EdgeTTSProvider,
}


class TTSProviderChain:
    """Tries the primary TTS provider, then the fallback, in order."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._providers: list[TTSProvider] = []
        for provider_name in (cfg.tts.primary_provider, cfg.tts.fallback_provider):
            provider_cls = _PROVIDER_CLASSES.get(provider_name)
            if provider_cls is None:
                continue
            if not provider_cls.is_configured():
                logger.info("TTS provider '%s' not configured; skipping", provider_name)
                continue
            self._providers.append(provider_cls(cfg))

        if not self._providers:
            # Edge TTS needs no API key, so this should be rare, but guard anyway.
            raise ProviderError(
                "No TTS providers are available. Check config.tts and SETUP.md, "
                "or run with --offline to smoke-test without real narration."
            )

    def synthesize(self, text: str, *, out_path: str) -> TTSResult:
        """Try each provider in order until one produces audio."""
        last_error: Exception | None = None
        for provider in self._providers:
            voice = self._cfg.tts.gemini_voice if provider.name == "gemini_tts" else self._cfg.tts.voice
            try:
                result = provider.synthesize(
                    text,
                    voice=voice,
                    rate=self._cfg.tts.speaking_rate,
                    out_path=out_path,
                )
                logger.info("Narration synthesized by TTS provider '%s'", provider.name)
                return result
            except RateLimitError as exc:
                logger.warning("TTS provider '%s' rate-limited: %s", provider.name, exc)
                last_error = exc
                time.sleep(self._cfg.rate_limits.rate_limit_backoff_seconds)
            except Exception as exc:  # noqa: BLE001
                logger.warning("TTS provider '%s' failed: %s", provider.name, exc)
                last_error = exc
        raise ProviderError(f"All TTS providers failed. Last error: {last_error}")
