"""Validate a rendered MP4 before it's allowed to be uploaded."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from config.settings import Config


class ValidationError(Exception):
    """Raised when the rendered output fails a pre-upload check."""


_MIN_FILE_SIZE_BYTES = 100 * 1024
_DURATION_TOLERANCE_SECONDS = 1.5


def _ffprobe_json(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def validate_output(path: Path, cfg: Config, expected_duration: float | None = None) -> None:
    """
    Run all pre-upload checks. Raises ValidationError on the first
    failure with a message explaining exactly what's wrong.
    """
    if not path.exists() or path.stat().st_size == 0:
        raise ValidationError(f"Output file missing or empty: {path}")
    if path.stat().st_size < _MIN_FILE_SIZE_BYTES:
        raise ValidationError(
            f"Output file is only {path.stat().st_size} bytes — expected at "
            f"least {_MIN_FILE_SIZE_BYTES} bytes (100 KB)."
        )

    try:
        probe = _ffprobe_json(path)
    except subprocess.CalledProcessError as exc:
        raise ValidationError(f"ffprobe could not read {path}: {exc}") from exc

    duration = float(probe.get("format", {}).get("duration", 0))
    if duration <= 0 or duration > cfg.video.max_duration_seconds:
        raise ValidationError(
            f"Output duration {duration:.1f}s is invalid or exceeds the "
            f"{cfg.video.max_duration_seconds}s Shorts limit."
        )
    if expected_duration is not None and abs(duration - expected_duration) > _DURATION_TOLERANCE_SECONDS:
        raise ValidationError(
            f"Output duration {duration:.1f}s deviates from the narration "
            f"duration {expected_duration:.1f}s by more than "
            f"{_DURATION_TOLERANCE_SECONDS}s."
        )

    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        raise ValidationError(f"Output has {len(video_streams)} video streams; expected exactly 1: {path}")
    if len(audio_streams) != 1:
        raise ValidationError(f"Output has {len(audio_streams)} audio streams; expected exactly 1: {path}")

    video_stream = video_streams[0]
    audio_stream = audio_streams[0]
    if video_stream.get("codec_name") != "h264":
        raise ValidationError(
            f"Video codec is '{video_stream.get('codec_name')}', expected 'h264'."
        )
    if audio_stream.get("codec_name") != "aac":
        raise ValidationError(
            f"Audio codec is '{audio_stream.get('codec_name')}', expected 'aac'."
        )

    width, height = video_stream.get("width"), video_stream.get("height")
    expected_w, expected_h = cfg.video.resolution
    if (width, height) != (expected_w, expected_h):
        raise ValidationError(
            f"Output resolution {width}x{height} does not match configured "
            f"{expected_w}x{expected_h}."
        )
