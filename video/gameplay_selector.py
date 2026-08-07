"""
Gameplay clip selection.

Picks a random file from `assets/gameplay/`, a random valid start
timestamp within it, and avoids picking the same file twice in a row
by remembering the last choice in a small state file.
"""

from __future__ import annotations

import json
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config

logger = get_logger(__name__)

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
_STATE_FILE = Path("temp") / "last_gameplay.json"


class NoGameplayAssetsError(Exception):
    """Raised when assets/gameplay/ has no usable video files."""


@dataclass(frozen=True)
class GameplayClip:
    path: Path
    start_seconds: float


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _load_last_used() -> str | None:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8")).get("last_file")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_last_used(filename: str) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"last_file": filename}), encoding="utf-8")


def select_gameplay(cfg: Config, needed_duration: float) -> GameplayClip:
    """
    Pick a random gameplay clip long enough for `needed_duration`,
    avoiding the same file used in the previous run when possible.
    """
    gameplay_dir = Path(cfg.video.gameplay_dir)
    candidates = [p for p in gameplay_dir.glob("*") if p.suffix.lower() in _VIDEO_EXTENSIONS]
    if not candidates:
        raise NoGameplayAssetsError(
            f"No video files found in {gameplay_dir}. Add gameplay clips there — see SETUP.md."
        )

    if cfg.video.avoid_repeat_gameplay and len(candidates) > 1:
        last_used = _load_last_used()
        filtered = [p for p in candidates if p.name != last_used]
        if filtered:
            candidates = filtered

    random.shuffle(candidates)
    for clip_path in candidates:
        try:
            duration = _probe_duration(clip_path)
        except (subprocess.CalledProcessError, ValueError) as exc:
            logger.warning("Skipping unreadable gameplay clip %s: %s", clip_path, exc)
            continue
        if duration >= needed_duration + 1.0:
            start = random.uniform(0, duration - needed_duration - 1.0)
            _save_last_used(clip_path.name)
            return GameplayClip(path=clip_path, start_seconds=start)

    raise NoGameplayAssetsError(
        f"No gameplay clip in {gameplay_dir} is long enough for a "
        f"{needed_duration:.1f}s narration."
    )
