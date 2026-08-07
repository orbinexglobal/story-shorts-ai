"""
FFmpeg render pipeline.

One render pass only, per the spec — no intermediate re-encodes.
Crops/scales the gameplay clip to the target vertical resolution, cuts
it to the narration length, mixes narration over background music
(with fade in/out and a configurable volume offset), and burns in the
ASS subtitles.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config
from video.subtitles import CARD_H, CARD_W, CARD_X, CARD_Y

logger = get_logger(__name__)


class RenderError(Exception):
    """Raised when the ffmpeg render process fails."""


def _escape_for_filter(path: Path) -> str:
    """Escape a filesystem path for safe use inside an ffmpeg filtergraph."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render_video(
    *,
    gameplay_path: Path,
    gameplay_start: float,
    duration: float,
    narration_path: Path,
    music_path: Path | None,
    ass_path: Path,
    cfg: Config,
    out_path: Path,
) -> Path:
    """Render the final vertical Short in a single ffmpeg pass."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = cfg.video.resolution
    fade_s = cfg.video.music_fade_seconds
    music_gain_db = cfg.video.music_volume_db
    ass_filter_path = _escape_for_filter(ass_path)

    inputs = [
        # Fast-seek into the gameplay clip before decoding so we don't
        # chew through the whole source file to reach the start offset.
        "-ss", f"{gameplay_start}",
        "-i", str(gameplay_path),
        "-i", str(narration_path),
    ]
    if music_path is not None:
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]

    video_chain = (
        f"[0:v]trim=start=0:duration={duration},setpts=PTS-STARTPTS,"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"drawbox=x={CARD_X}:y={CARD_Y}:w={CARD_W}:h={CARD_H}:"
        f"color=black@{cfg.subtitles.card_alpha}:t=fill,"
        f"ass='{ass_filter_path}'[vout]"
    )

    if music_path is not None:
        audio_chain = (
            f"[2:a]volume={music_gain_db}dB,"
            f"afade=t=in:st=0:d={fade_s},afade=t=out:st={max(duration - fade_s, 0)}:d={fade_s}[music];"
            f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
    else:
        audio_chain = f"[1:a]volume=1.0[aout]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", f"{video_chain};{audio_chain}",
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{duration}",
        "-r", str(cfg.video.fps),
        "-c:v", "libx264", "-preset", str(cfg.video.render_preset), "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_path),
    ]

    logger.info("Rendering %s (%ss)", out_path, f"{duration:.1f}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffmpeg render failed:\n{result.stderr[-2000:]}")
    return out_path
