"""Tests for utils/saga_state.py — the "Parts 1..N" subscriber loop state."""
import json
from dataclasses import replace
from pathlib import Path

from config.settings import load_config
from utils.saga_state import (
    advance_saga,
    build_saga_context,
    build_saga_line,
    load_saga,
)


def _cfg(tmp_path, enabled=True, parts=3, state=None, name="saga_state.json"):
    cfg = load_config()
    state_path = tmp_path / name
    if state is not None:
        state_path.write_text(json.dumps(state))
    story = replace(
        cfg.story,
        saga=replace(
            cfg.story.saga,
            enabled=enabled,
            parts_per_saga=parts,
            state_file=str(state_path),
        ),
    )
    return replace(cfg, story=story), state_path


def test_fresh_state_when_file_missing(tmp_path):
    assert load_saga(tmp_path / "missing.json").part_number == 1


def test_advance_persists_and_increments(tmp_path):
    cfg, path = _cfg(tmp_path, parts=3)
    advance_saga("chapter one", cfg, path)
    state = load_saga(path)
    assert state.part_number == 2
    assert state.last_story == "chapter one"


def test_final_part_resets_to_new_saga(tmp_path):
    cfg, path = _cfg(tmp_path, parts=3, state={"part_number": 3, "last_story": "chapter two"})
    advance_saga("chapter three", cfg, path)
    state = load_saga(path)
    assert state.part_number == 1
    assert state.last_story == ""


def test_infinite_mode_never_resets(tmp_path):
    cfg, path = _cfg(tmp_path, parts=0)
    advance_saga("a", cfg, path)
    advance_saga("b", cfg, path)
    assert load_saga(path).part_number == 3


def test_disabled_saga_builds_empty_context(tmp_path):
    cfg, _ = _cfg(tmp_path, enabled=False)
    assert build_saga_context(cfg) == ""
    assert build_saga_line(cfg) == ""


def test_part_one_context_opens_new_saga_and_teases_part_two(tmp_path):
    cfg, _ = _cfg(tmp_path, parts=3)
    ctx = build_saga_context(cfg)
    assert "FIRST part" in ctx
    assert "Part 2 drops tomorrow" in ctx
    assert "must NOT fully resolve" in ctx


def test_continuation_context_carries_previous_story(tmp_path):
    cfg, path = _cfg(tmp_path, parts=3)
    advance_saga("I found a second key under his bed.", cfg, path)
    ctx = build_saga_context(cfg, path)
    assert "second key under his bed" in ctx
    assert "Part 3 drops tomorrow" in ctx  # advance() made next part = 3


def test_final_part_context_requires_resolution(tmp_path):
    cfg, path = _cfg(tmp_path, parts=3, state={"part_number": 3, "last_story": "x"})
    ctx = build_saga_context(cfg, path)
    assert "FINAL part" in ctx
    assert "Resolve the mystery COMPLETELY" in ctx


def test_saga_lines_guide_the_subscription_message(tmp_path):
    cfg, path = _cfg(tmp_path, parts=3, name="mid.json")
    assert "Part 2 drops tomorrow" in build_saga_line(cfg, path)

    advance_saga("one", cfg, path)
    assert "Part 2 of 3" in build_saga_line(cfg, path)

    final_cfg, final_path = _cfg(tmp_path, parts=3, state={"part_number": 3, "last_story": "x"}, name="final.json")
    assert "the ending is here" in build_saga_line(final_cfg, final_path)

    inf_cfg, inf_path = _cfg(tmp_path, parts=0, name="infinite.json")
    advance_saga("one", inf_cfg, inf_path)
    assert "Part 2." in build_saga_line(inf_cfg, inf_path)


def test_metadata_gets_part_suffix_and_saga_line(tmp_path):
    import json as _json

    from providers.base import TextProvider
    from providers.metadata_generator import generate_metadata

    class _Stub(TextProvider):
        name = "stub"

        def generate(self, prompt: str, *, max_tokens: int = 800) -> str:
            return _json.dumps({
                "titles": ["The Lock That Hated Being Alone"],
                "description": "A basement lock had one very specific rule.",
                "hashtags": ["#TinyPopTV", "#storytime"],
            })

    cfg, path = _cfg(tmp_path, parts=3, state={"part_number": 2, "last_story": ""})
    metadata = generate_metadata(_Stub(), "Some story here", part_number=2, saga_line=build_saga_line(cfg, path))
    assert " (Part 2)" in metadata.title
    assert "Part 2 of 3" in metadata.description