"""
Story generation and scoring.

Generates `config.story.candidates_per_run` independent story
candidates, has each one self-scored by the model across six
dimensions (hook, curiosity, emotional flow, ending, simplicity,
retention), and keeps only the highest-scoring one — discarding the
rest, per the project spec. If the best candidate doesn't clear
`config.story.min_acceptable_score`, the run is aborted rather than
publishing a weak story.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import TextProvider
from utils.json_extract import JsonExtractionError, extract_json

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "story_prompt.txt"
_SCORE_FIELDS = (
    "hook_score", "curiosity_score", "emotional_flow_score",
    "ending_score", "simplicity_score", "retention_score",
)
_MAX_ATTEMPTS = 3

# Non-Latin scripts (CJK, Cyrillic, Arabic, etc.) occasionally leak into
# free-model output as tokenizer garbage. The narration must be clean,
# readable English, so such stories are rejected and regenerated.
_GARBAGE_SCRIPT = re.compile(
    r"[\u0400-\u04FF"      # Cyrillic
    r"\u4E00-\u9FFF"       # CJK
    r"\u0600-\u06FF"       # Arabic
    r"\u0B80-\u0BFF"       # Tamil
    r"\u0E00-\u0E7F"       # Thai
    r"\u0900-\u097F"       # Devanagari
    r"]"
)


class StoryQualityError(Exception):
    """Raised when no generated candidate clears the quality threshold."""


@dataclass(frozen=True)
class StoryCandidate:
    text: str
    scores: dict[str, float]

    @property
    def overall_score(self) -> float:
        return sum(self.scores.values()) / len(self.scores)


def _build_prompt(cfg: Config) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(min_seconds=cfg.story.min_seconds, max_seconds=cfg.story.max_seconds)


def generate_story(text_provider: TextProvider, cfg: Config) -> StoryCandidate:
    """
    Generate several story candidates, score them, and return the best.

    Retries up to `_MAX_ATTEMPTS` rounds: unparseable, non-Latin-garbage,
    or low-scoring outputs are discarded and the provider is asked again
    (the text chain falls through to another model on repeated failure).

    Raises:
        StoryQualityError: if no clean candidate clears the threshold.
    """
    prompt = _build_prompt(cfg)

    for round_no in range(1, _MAX_ATTEMPTS + 1):
        candidates: list[StoryCandidate] = []

        for i in range(cfg.story.candidates_per_run):
            # Thinking models spend tokens on reasoning before emitting text, so
            # a generous output cap is required to avoid truncated JSON.
            raw = text_provider.generate(prompt, max_tokens=8192)
            try:
                parsed = extract_json(raw)
                story_text = str(parsed["story"]).strip()
                scores = {field: float(parsed[field]) for field in _SCORE_FIELDS}
            except (JsonExtractionError, KeyError, ValueError) as exc:
                logger.warning(
                    "Round %d, candidate %d/%d unparseable: %s",
                    round_no, i + 1, cfg.story.candidates_per_run, exc,
                )
                continue

            if not story_text or _GARBAGE_SCRIPT.search(story_text):
                logger.warning(
                    "Round %d, candidate %d/%d discarded: non-Latin garbage",
                    round_no, i + 1, cfg.story.candidates_per_run,
                )
                continue

            candidate = StoryCandidate(text=story_text, scores=scores)
            candidates.append(candidate)
            logger.info(
                "Round %d, candidate %d/%d generated, overall_score=%.1f",
                round_no, i + 1, cfg.story.candidates_per_run, candidate.overall_score,
            )

        if not candidates:
            logger.warning("Attempt %d/%d produced no usable candidate", round_no, _MAX_ATTEMPTS)
            continue

        best = max(candidates, key=lambda c: c.overall_score)
        if best.overall_score < cfg.story.min_acceptable_score:
            logger.warning(
                "Attempt %d/%d: best candidate scored %.1f (below %.1f); retrying",
                round_no, _MAX_ATTEMPTS, best.overall_score, cfg.story.min_acceptable_score,
            )
            continue

        logger.info(
            "Selected best candidate (score=%.1f) out of %d",
            best.overall_score, len(candidates),
        )
        return best

    raise StoryQualityError(
        f"No clean story cleared the {cfg.story.min_acceptable_score:.1f} "
        "quality threshold after multiple attempts."
    )
