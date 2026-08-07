"""
Video metadata generation: title, description, hashtags.

Both prompts ask the model for several candidates and this module
enforces the hard rules from the spec (title length, no ALL CAPS) in
code rather than trusting the model to always comply.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.logging_setup import get_logger
from providers.base import TextProvider
from utils.json_extract import JsonExtractionError, extract_json

logger = get_logger(__name__)

_TITLE_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "title_prompt.txt"
_DESC_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "description_prompt.txt"

_MIN_TITLE_LEN = 25
_MAX_TITLE_LEN = 55


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    description: str
    hashtags: list[str]

    @property
    def full_description(self) -> str:
        return f"{self.description}\n\n{' '.join(self.hashtags)}"


def _pick_best_title(titles: list[str], fallback_story: str) -> str:
    """Prefer a title within the length window; otherwise trim the first one."""
    for title in titles:
        cleaned = title.strip()
        if not cleaned.isupper() and _MIN_TITLE_LEN <= len(cleaned) <= _MAX_TITLE_LEN:
            return cleaned
    if titles:
        return titles[0].strip()[: _MAX_TITLE_LEN]
    return fallback_story[: _MAX_TITLE_LEN]


def generate_metadata(text_provider: TextProvider, story: str) -> VideoMetadata:
    """Generate a title, description, and hashtags for the given story."""
    title_prompt = _TITLE_PROMPT_PATH.read_text(encoding="utf-8").format(story=story)
    desc_prompt = _DESC_PROMPT_PATH.read_text(encoding="utf-8").format(story=story)

    try:
        title_data = extract_json(text_provider.generate(title_prompt, max_tokens=2048))
        titles = [str(t) for t in title_data.get("titles", [])]
    except JsonExtractionError as exc:
        logger.warning("Falling back to a generic title: %s", exc)
        titles = []
    title = _pick_best_title(titles, story)

    try:
        desc_data = extract_json(text_provider.generate(desc_prompt, max_tokens=2048))
        description = str(desc_data.get("description", story[:150]))
        hashtags = [str(h) for h in desc_data.get("hashtags", ["#shorts"])]
    except JsonExtractionError as exc:
        logger.warning("Falling back to a generic description: %s", exc)
        description = story[:150]
        hashtags = ["#shorts", "#storytime"]

    return VideoMetadata(title=title, description=description, hashtags=hashtags)
