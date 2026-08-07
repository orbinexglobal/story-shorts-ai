"""
Per-provider API rate limiting.

Keeps the pipeline within each provider's free-tier request-per-minute
limits so bursts of calls (e.g. generating several story candidates
back to back) don't trip HTTP 429 responses. A single process-wide
limiter is kept per provider name; every provider call waits its turn
before hitting the API.

Free-tier ballpark (check the provider docs — these change):
    Gemini (gemini-2.5-flash): 5 RPM / 125 RPD
    OpenRouter free models:    50 free requests/day per model
    Groq (most models):        30 RPM / 14,400 RPD
"""

from __future__ import annotations

import random
import threading
import time

_JITTER_FRACTION = 0.15
_DEFAULT_REQUESTS_PER_MINUTE = 5

_LOCK = threading.Lock()
_LIMITERS: dict[str, "_RateLimiter"] = {}


class _RateLimiter:
    """Spaces calls out so the average rate never exceeds RPM, with jitter."""

    def __init__(self, requests_per_minute: int) -> None:
        self._min_interval = 60.0 / max(requests_per_minute, 1)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next_allowed - now
            if delay > 0:
                time.sleep(delay)
            interval = self._min_interval * (1.0 + random.random() * _JITTER_FRACTION)
            self._next_allowed = max(now + interval, self._next_allowed + interval)


def throttle(name: str, requests_per_minute: int | None = None) -> None:
    """Block until this process is allowed to make another call to `name`."""
    rpm = requests_per_minute or _DEFAULT_REQUESTS_PER_MINUTE
    with _LOCK:
        limiter = _LIMITERS.get(name)
        if limiter is None:
            limiter = _RateLimiter(rpm)
            _LIMITERS[name] = limiter
    limiter.wait()


def is_rate_limit(status_code: int) -> bool:
    """True when a provider response is a rate-limit / quota error."""
    return status_code == 429
