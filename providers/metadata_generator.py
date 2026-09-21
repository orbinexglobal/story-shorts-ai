"""
Video metadata generation: title, description, hashtags.

The prompt asks the model for 5 title candidates plus a description and
hashtags, and this module returns the best title candidate while enforcing
the hard rules from the spec (title length, no ALL CAPS) in code rather
than trusting the model to always comply.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.logging_setup import get_logger
from providers.base import TextProvider
from utils.json_extract import JsonExtractionError, extract_json

logger = get_logger(__name__)

_METADATA_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "metadata_prompt.txt"

_MIN_TITLE_LEN = 25
_MAX_TITLE_LEN = 55

_DEFAULT_DESCRIPTION_SUFFIX = (
    "What would you have done? Follow TinyPop TV for a new story every day."
)


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    description: str
    hashtags: list[str]

    @property
    def full_description(self) -> str:
        return f"{self.description}\n\n{' '.join(self.hashtags)}"


def _truncate_cleanly(text: str, max_len: int) -> str:
    """Truncate without splitting a word, preferring a sentence boundary.

    Only used on the fallback path (non-JSON model output), where a raw
    ``text[:max_len]`` cut can produce an ugly mid-sentence title.
    """
    text = text.strip()
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end > max_len * 0.5:
        return window[: sentence_end + 1].rstrip()
    word_end = window.rfind(" ")
    if word_end > 0:
        return window[:word_end].rstrip(",.;:") + "\u2026"
    return window.rstrip(",.;:") + "\u2026"


def _pick_best_title(titles: list[str], fallback_story: str) -> str:
    """Prefer a title within the length window; otherwise trim the first one."""
    for title in titles:
        cleaned = title.strip()
        if not cleaned.isupper() and _MIN_TITLE_LEN <= len(cleaned) <= _MAX_TITLE_LEN:
            return cleaned
    if titles:
        return _truncate_cleanly(titles[0], _MAX_TITLE_LEN)
    return _truncate_cleanly(fallback_story, _MAX_TITLE_LEN)


def _apply_part_suffix(title: str, part_number: int | None) -> str:
    """Append ' (Part N)' to saga titles so the series is findable."""
    if not part_number:
        return title
    suffix = f" (Part {part_number})"
    if f"part {part_number}" in title.lower():
        return title
    base = _truncate_cleanly(title, _MAX_TITLE_LEN - len(suffix))
    return f"{base}{suffix}"


def generate_metadata(
    text_provider: TextProvider,
    story: str,
    part_number: int | None = None,
    saga_line: str = "",
) -> VideoMetadata:
    """
    Generate a title, description, and hashtags for the given story.

    A single provider call produces all three, so a Short's metadata costs
    one API request instead of two. Saga parts get a "(Part N)" title suffix
    and the deterministic `saga_line` appended to the description (built in
    code so the subscribe mechanic is never left up to the model).
    """
    prompt = _METADATA_PROMPT_PATH.read_text(encoding="utf-8").format(story=story)

    try:
        data = extract_json(text_provider.generate(prompt, max_tokens=2048))
        titles = [str(t) for t in data.get("titles", [])]
    except JsonExtractionError as exc:
        logger.warning("Falling back to a generic title: %s", exc)
        data = {}
        titles = []
    title = _pick_best_title(titles, story)
    title = _apply_part_suffix(title, part_number)

    description = str(data.get("description", "")).strip()
    if not description:
        description = f"{story[:150]}. {_DEFAULT_DESCRIPTION_SUFFIX}"
    if saga_line:
        description = f"{description}\n\n{saga_line}"

    hashtags = [str(h) for h in data.get("hashtags", [])]
    if not hashtags:
        hashtags = ["#TinyPopTV", "#storytime"]

    return VideoMetadata(title=title, description=description, hashtags=hashtags)