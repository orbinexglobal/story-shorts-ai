"""
Saga serialization state — the "subscribe to catch the ending" engine.

To manufacture subscribers, stories are chained into open-loop parts: each
upload is Part N of a saga, ends on a cliffhanger with "Part N+1 drops
tomorrow — follow so you don't miss it", and only resolves after
`config.story.saga.parts_per_saga` parts (or never, when parts_per_saga = 0).

The chain state lives in a small JSON file committed by the workflow between
runs (like `daily_upload_count.json`), so successive GitHub Actions runs
continue the same story instead of starting fresh each time.

Only advance the saga AFTER an upload actually succeeds, and never in test
mode, so render failures or local runs can't skip a part.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config

logger = get_logger(__name__)

_STATE_FILE = Path("state") / "saga_state.json"


@dataclass(frozen=True)
class SagaContext:
    """Read-only description of the part the NEXT story should be."""

    part_number: int        # 1-based part number of the upcoming story
    is_new_saga: bool       # True when this is part 1 of a fresh chain
    is_final_part: bool     # True when this part resolves the saga
    total_parts: int | None  # None when parts_per_saga = 0 (perpetual series)
    last_story: str = ""    # the narration of the previous part (continuity)


@dataclass
class SagaState:
    """Persisted saga position. `last_story` carries continuity between parts."""

    part_number: int = 1      # the part number the NEXT story will be
    last_story: str = ""      # previous narration text (continuity for Part 2+)

    def to_dict(self) -> dict:
        return {"part_number": self.part_number, "last_story": self.last_story}

    @classmethod
    def from_dict(cls, data: dict) -> "SagaState":
        return cls(
            part_number=int(data.get("part_number", 1)),
            last_story=str(data.get("last_story", "")),
        )

    def context(self, cfg: Config) -> SagaContext:
        parts_per_saga = cfg.story.saga.parts_per_saga
        is_final = parts_per_saga > 0 and self.part_number >= parts_per_saga
        return SagaContext(
            part_number=self.part_number,
            is_new_saga=self.part_number <= 1,
            is_final_part=is_final,
            total_parts=parts_per_saga if parts_per_saga > 0 else None,
            last_story=self.last_story,
        )


def load_saga(path: Path = _STATE_FILE) -> SagaState:
    """Load the saga state from disk (fresh saga if the file is missing/corrupt)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = SagaState.from_dict(data)
        logger.info("Saga state loaded: next part %d", state.part_number)
        return state
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        logger.info("No saga state on disk; starting a fresh saga.")
        return SagaState()


def advance_saga(new_story: str, cfg: Config, path: Path = _STATE_FILE) -> SagaState:
    """
    Persist that the current part was published and return the next state.

    After a saga's final part resolves, the state is reset so the next story
    starts a brand-new chain.
    """
    parts_per_saga = cfg.story.saga.parts_per_saga
    current = load_saga(path)

    if parts_per_saga > 0 and current.part_number >= parts_per_saga:
        logger.info("Saga part %d/%d resolved; next story starts a new saga.",
                    current.part_number, parts_per_saga)
        next_state = SagaState()
    else:
        next_state = SagaState(part_number=current.part_number + 1, last_story=new_story)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(next_state.to_dict()), encoding="utf-8")
    logger.info("Saga advanced to part %d", next_state.part_number)
    return next_state


def build_saga_context(cfg: Config, path: Path | None = None) -> str:
    """
    Build the `{saga_context}` block injected into the story prompt, or "" when
    saga mode is disabled. The block overrides the prompt's generic ending
    rules so parts end on cliffhangers that force subscriptions.
    """
    saga = cfg.story.saga
    if not saga.enabled:
        return ""
    state = load_saga(path or Path(saga.state_file))
    ctx = state.context(cfg)

    if ctx.is_new_saga:
        total_line = f" of {ctx.total_parts}" if ctx.total_parts else ""
        return (
            f"This is the FIRST part{total_line} of a continuing story.\n"
            "End this part with a twist that opens an even BIGGER mystery "
            "(a hard cliffhanger) — the story must NOT fully resolve.\n"
            'Final spoken line must be: "Part 2 drops tomorrow — follow '
            'TinyPop TV so you don\'t miss it."'
        )

    total_line = f" of {ctx.total_parts}" if ctx.total_parts else ""
    prompt = (
        f"This is part {ctx.part_number} of an ongoing story. "
        f"Next up: part {ctx.part_number + 1}{total_line}.\n"
        "STORY SO FAR — continue THIS EXACT plot, do not restart it:\n"
        f'"{ctx.last_story[:500]}"\n'
        "Continue the exact same plot, same first-person narrator, same "
        "characters and objects. Do NOT re-explain the setup.\n"
    )
    if ctx.is_final_part:
        prompt += (
            f"This is the FINAL part ({ctx.part_number} of {ctx.total_parts}).\n"
            "Resolve the mystery COMPLETELY — no cliffhanger, a definite "
            'ending. Then add one normal follow line like "Follow TinyPop TV '
            'for more stories."'
        )
    else:
        prompt += (
            "End this part on a HARD cliffhanger — cut off at the single most "
            f'dramatic moment.\nFinal spoken line must be: "Part '
            f'{ctx.part_number + 1} drops tomorrow — follow TinyPop TV so you '
            "don't miss it.\""
        )
    return prompt


def build_saga_line(cfg: Config, path: Path | None = None) -> str:
    """
    Return the deterministic part line appended to the video description
    (e.g. "Part 2 of 3. Part 3 drops tomorrow — follow so you don't miss the
    ending."), or "" when saga mode is disabled. Built in code so the
    subscribe mechanic is guaranteed, never left to the model.
    """
    saga = cfg.story.saga
    if not saga.enabled:
        return ""
    state = load_saga(path or Path(saga.state_file))
    ctx = state.context(cfg)

    if ctx.is_new_saga:
        return "This story continues — Part 2 drops tomorrow. Follow TinyPop TV so you don't miss it."
    if ctx.is_final_part and ctx.total_parts:
        return f"Part {ctx.part_number} of {ctx.total_parts} — the ending is here."
    if ctx.total_parts:
        return (
            f"Part {ctx.part_number} of {ctx.total_parts}. Part {ctx.part_number + 1} "
            "drops tomorrow — follow so you don't miss the ending."
        )
    return f"Part {ctx.part_number}. Part {ctx.part_number + 1} drops tomorrow — follow so you don't miss the ending."