"""
Small helper for pulling a JSON object out of raw LLM text output.

Models sometimes wrap JSON in markdown fences or add stray text before
or after it despite instructions not to. This extracts the first
top-level `{...}` object and parses it, raising a clear error if that
fails, rather than letting a JSONDecodeError bubble up unexplained.
"""

from __future__ import annotations

import json
from typing import Any


class JsonExtractionError(Exception):
    """Raised when no valid JSON object can be found in the text."""


def extract_json(text: str) -> dict[str, Any]:
    """Find and parse the first JSON object in `text`."""
    if not text:
        raise JsonExtractionError("No JSON object found in empty text")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise JsonExtractionError(f"No JSON object found in text: {text[:200]!r}")

    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise JsonExtractionError(f"Could not parse JSON: {exc}. Text: {candidate[:200]!r}") from exc
