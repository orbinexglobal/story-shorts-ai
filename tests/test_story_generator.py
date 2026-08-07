"""Tests for providers/story_generator.py, using a stub TextProvider."""

import json

import pytest

from config.settings import load_config
from providers.base import TextProvider
from providers.story_generator import StoryQualityError, generate_story


class _StubProvider(TextProvider):
    name = "stub"

    def __init__(self, responses):
        self._responses = iter(responses)

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        return next(self._responses)


def _story_json(score: float) -> str:
    return json.dumps({
        "story": "A tiny robot learns to say hello.",
        "hook_score": score, "curiosity_score": score,
        "emotional_flow_score": score, "ending_score": score,
        "simplicity_score": score, "retention_score": score,
    })


def test_generate_story_picks_the_best_candidate():
    cfg = load_config()
    provider = _StubProvider([_story_json(8.0), _story_json(9.0), _story_json(7.0)][: cfg.story.candidates_per_run])
    best = generate_story(provider, cfg)
    assert best.overall_score >= 7.0


def test_generate_story_raises_below_threshold():
    cfg = load_config()
    low_scores = [_story_json(1.0) for _ in range(cfg.story.candidates_per_run * 3)]
    provider = _StubProvider(low_scores)
    with pytest.raises(StoryQualityError):
        generate_story(provider, cfg)
