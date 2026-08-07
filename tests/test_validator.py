"""Tests for video/validator.py."""

import subprocess
from pathlib import Path

import pytest

from config.settings import load_config
from video.validator import ValidationError, validate_output


@pytest.fixture()
def cfg():
    return load_config()


def _synthetic_video(path: Path, duration: float = 2.0) -> Path:
    """Render a tiny, correctly-encoded 1080x1920 clip to validate against."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc2=size=1080x1920:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440",
            "-t", f"{duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(path),
        ],
        capture_output=True, check=True,
    )
    return path


def test_validate_output_accepts_good_file(tmp_path, cfg):
    video = _synthetic_video(tmp_path / "good.mp4", duration=2.0)
    validate_output(video, cfg, expected_duration=2.0)


def test_validate_output_rejects_tiny_file(tmp_path, cfg):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"x" * 1024)
    with pytest.raises(ValidationError, match="100 KB"):
        validate_output(tiny, cfg)


def test_validate_output_rejects_duration_deviation(tmp_path, cfg):
    video = _synthetic_video(tmp_path / "long.mp4", duration=3.0)
    with pytest.raises(ValidationError, match="deviates"):
        validate_output(video, cfg, expected_duration=0.5)


def test_validate_output_rejects_missing_file(tmp_path, cfg):
    with pytest.raises(ValidationError, match="missing or empty"):
        validate_output(tmp_path / "nope.mp4", cfg)
