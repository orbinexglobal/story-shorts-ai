"""Background music selection from assets/music/."""

from __future__ import annotations

import random
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config

logger = get_logger(__name__)

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}


def select_music(cfg: Config) -> Path | None:
    """
    Pick a random background music track.

    Music is optional: returns None when assets/music/ has no usable
    audio files so the pipeline can render narration-only shorts.
    """
    music_dir = Path(cfg.video.music_dir)
    candidates = [p for p in music_dir.glob("*") if p.suffix.lower() in _AUDIO_EXTENSIONS]
    if not candidates:
        logger.info("No audio files found in %s — rendering without background music.", music_dir)
        return None
    return random.choice(candidates)
