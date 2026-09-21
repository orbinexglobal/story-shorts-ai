"""Tests for providers/metadata_generator.py, using a stub TextProvider."""

import json

from config.settings import load_config
from providers.base import TextProvider
from providers.metadata_generator import _MAX_TITLE_LEN, _MIN_TITLE_LEN, generate_metadata


class _StubProvider(TextProvider):
    name = "stub"

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
        self.calls += 1
        return self._response


def _metadata_json() -> str:
    return json.dumps({
        "titles": [
            "The Basement Window That Showed My Own Face",
            "The Photo That Knew I Was Home",
            "too short",
            "The Neighbor Who Watched Me Sleep Last Night",
        ],
        "description": "A neighbor's one rule had a very dark reason.",
        "hashtags": ["#TinyPopTV", "#storytime", "#paranormal"],
    })


def test_generate_metadata_makes_a_single_api_call():
    cfg = load_config()
    provider = _StubProvider(_metadata_json())
    metadata = generate_metadata(provider, "Some story here")

    assert provider.calls == 1
    title_in_window = _MIN_TITLE_LEN <= len(metadata.title) <= _MAX_TITLE_LEN
    assert title_in_window
    assert not metadata.title.isupper()
    assert "dark reason" in metadata.description
    assert metadata.hashtags[0] == "#TinyPopTV"
    assert "#TinyPopTV" in metadata.full_description


def test_generate_metadata_falls_back_on_garbage():
    provider = _StubProvider("this is not json")
    metadata = generate_metadata(provider, "A tiny robot learns to say hello.")

    assert _MIN_TITLE_LEN <= len(metadata.title) <= _MAX_TITLE_LEN
    assert metadata.description  # non-empty fallback description
    assert metadata.hashtags  # non-empty fallback hashtags


def test_fallback_title_truncates_at_sentence_boundary():
    story = (
        "The key only worked when I was alone. I found it in my coat. "
        "Each turn made the lights flicker. On the third turn, a whisper "
        "called my name."
    )
    metadata = generate_metadata(_StubProvider("no json here"), story)

    assert metadata.title == "The key only worked when I was alone."
    assert _MIN_TITLE_LEN <= len(metadata.title) <= _MAX_TITLE_LEN
    assert "\u2026" not in metadata.title


def test_fallback_title_ellipsizes_when_no_sentence_boundary():
    story = "P" * 30 + " then one very long unbroken sentence with no punctuation"
    metadata = generate_metadata(_StubProvider("no json here"), story)

    assert len(metadata.title) <= _MAX_TITLE_LEN
    assert metadata.title.endswith("\u2026")