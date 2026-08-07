"""
Shared interfaces for text-generation and TTS providers.

Every concrete provider (Gemini, OpenRouter, Groq, Edge TTS, the
offline mock) implements one of these two small interfaces so the
fallback chains in text_chain.py / tts_chain.py can treat them
interchangeably.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(Exception):
    """Raised when a provider fails to produce a usable result."""


class RateLimitError(ProviderError):
    """Raised when a provider responds with an HTTP 429 (rate limit)."""


class TextProvider(ABC):
    """A provider that turns a prompt into generated text."""

    name: str

    @abstractmethod
    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        """
        Generate text for the given prompt.

        Raises:
            ProviderError: if the provider is unavailable or the request fails.
        """
        raise NotImplementedError


class WordTiming:
    """A single spoken word and its start/end times in the narration audio."""

    __slots__ = ("word", "start", "end")

    def __init__(self, word: str, start: float, end: float) -> None:
        self.word = word
        self.start = start
        self.end = end


class TTSResult:
    """Synthesized narration plus optional word-level timestamps."""

    __slots__ = ("duration", "word_timings")

    def __init__(self, duration: float, word_timings: list[WordTiming] | None = None) -> None:
        self.duration = duration
        self.word_timings = word_timings


class TTSProvider(ABC):
    """A provider that turns narration text into a narrated audio file."""

    name: str

    @abstractmethod
    def synthesize(self, text: str, *, voice: str, rate: float, out_path: str) -> TTSResult:
        """
        Synthesize speech for `text` and write it to `out_path` (WAV or MP3).

        Returns:
            A TTSResult with the audio duration in seconds and, when the
            provider can produce them, per-word start/end timestamps used
            for synced word-by-word captions.

        Raises:
            ProviderError: if synthesis fails.
        """
        raise NotImplementedError
