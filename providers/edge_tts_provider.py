"""
Microsoft Edge TTS provider.

Free, no API key required. Used as the reliable fallback (and, per
config, can be set as primary) behind the `edge-tts` PyPI package.
Captures word-boundary events while streaming so subtitles can be
synced to the exact words being spoken.
"""

from __future__ import annotations

import asyncio

from config.settings import Config
from providers.base import ProviderError, TTSProvider, TTSResult, WordTiming


class EdgeTTSProvider(TTSProvider):
    """Speech synthesis via Microsoft Edge's free TTS service."""

    name = "edge_tts"

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    @staticmethod
    def is_configured() -> bool:
        # No API key needed; only requires the edge-tts package + network.
        return True

    def synthesize(self, text: str, *, voice: str, rate: float, out_path: str) -> TTSResult:
        try:
            import edge_tts
        except ImportError as exc:
            raise ProviderError(
                "The 'edge-tts' package is not installed. Run "
                "`pip install -r requirements.txt`."
            ) from exc

        rate_str = f"{'+' if rate >= 1 else ''}{int((rate - 1) * 100)}%"
        boundaries: list[dict] = []

        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text, voice=voice, rate=rate_str, boundary="WordBoundary"
            )
            with open(out_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        boundaries.append(chunk)

        try:
            asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Edge TTS failed: {exc}") from exc

        word_timings = [_boundary_to_timing(b) for b in boundaries]
        return TTSResult(duration=_probe_duration(out_path), word_timings=word_timings)


def _boundary_to_timing(chunk: dict) -> WordTiming:
    """Convert an edge-tts WordBoundary chunk into a WordTiming."""
    # The word text carries a hidden sentinel character prefix.
    word = chunk["text"].lstrip("\x1f\x02").strip() or " "
    start = chunk["offset"] / 10_000_000  # offset is in 100-nanosecond ticks
    duration = chunk["duration"] / 10_000_000
    return WordTiming(word=word, start=start, end=start + duration)


def _probe_duration(path: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    import subprocess

    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())
