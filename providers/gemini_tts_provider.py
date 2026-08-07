"""
Google Gemini text-to-speech provider.

Uses Gemini's audio-output generateContent endpoint. Because exact
response shapes can shift between Gemini model versions, every failure
here is wrapped as a ProviderError so tts_chain.py can fall back to
Edge TTS without the pipeline ever crashing.
"""

from __future__ import annotations

import base64
import os
import wave

import requests

from config.settings import Config
from providers.base import ProviderError, RateLimitError, TTSProvider, TTSResult
from utils.rate_limit import is_rate_limit, throttle

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTTSProvider(TTSProvider):
    """Speech synthesis via a Gemini TTS-capable model."""

    name = "gemini_tts"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._api_key = os.environ.get("GEMINI_API_KEY")
        self._model = "gemini-2.5-flash-preview-tts"

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    def synthesize(self, text: str, *, voice: str, rate: float, out_path: str) -> TTSResult:
        if not self._api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

        throttle("gemini", self._cfg.rate_limits.rpm_for("gemini"))
        url = f"{_API_BASE}/{self._model}:generateContent?key={self._api_key}"
        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
                },
            },
        }
        try:
            response = requests.post(url, json=body, timeout=90)
            if is_rate_limit(response.status_code):
                raise RateLimitError(f"Gemini TTS rate limit (HTTP 429)")
            response.raise_for_status()
            data = response.json()
            audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        except RateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Gemini TTS failed: {exc}") from exc

        pcm_bytes = base64.b64decode(audio_b64)
        with wave.open(out_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)   # 16-bit PCM
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_bytes)

        duration = len(pcm_bytes) / 2 / 24000
        return TTSResult(duration=duration, word_timings=None)
