"""
Typed configuration loader for StoryShorts AI.

Every other module in the project should read settings through the
`Config` object returned by `load_config()` rather than reading
`config.yaml` directly or hardcoding values. This keeps all tunables
in one place and makes the pipeline behavior fully driven by config.

Usage:
    from config.settings import load_config

    cfg = load_config()
    print(cfg.video.fps)
    print(cfg.ai_providers.fallback_order)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


@dataclass(frozen=True)
class ScheduleConfig:
    """How many Shorts to make per run (one day's batch)."""

    shorts_per_day: int


@dataclass(frozen=True)
class StoryConfig:
    """Controls story generation constraints and scoring thresholds."""

    min_seconds: int
    max_seconds: int
    language: str
    tone: str
    candidates_per_run: int
    min_acceptable_score: float


@dataclass(frozen=True)
class ProviderModelConfig:
    """Preferred model list for a single AI provider."""

    preferred_models: list[str]


@dataclass(frozen=True)
class AIProvidersConfig:
    """Fallback order and per-provider model preferences."""

    fallback_order: list[str]
    max_retries_per_provider: int
    retry_backoff_seconds: int
    gemini: ProviderModelConfig
    openrouter: ProviderModelConfig
    groq: ProviderModelConfig


@dataclass(frozen=True)
class TTSConfig:
    """Text-to-speech provider and voice settings."""

    primary_provider: str
    fallback_provider: str
    voice: str
    gemini_voice: str
    speaking_rate: float


@dataclass(frozen=True)
class VideoConfig:
    """Rendering, asset, and output settings for the final MP4."""

    resolution: tuple[int, int]
    fps: int
    audio_codec: str
    video_codec: str
    render_preset: str
    max_duration_seconds: int
    gameplay_dir: str
    music_dir: str
    font_dir: str
    avoid_repeat_gameplay: bool
    music_volume_db: int
    music_fade_seconds: int


@dataclass(frozen=True)
class SubtitlesConfig:
    """Burned-in subtitle appearance (Reddit-post card style)."""

    words_per_group: int
    font_size: int
    font_color: str
    outline_color: str
    highlight_color: str
    card_alpha: float
    card_header: str


@dataclass(frozen=True)
class YouTubeConfig:
    """Upload metadata defaults for the YouTube Data API."""

    visibility: str
    category_id: str
    default_language: str
    made_for_kids: bool


@dataclass(frozen=True)
class LoggingConfig:
    """Log verbosity. Console only — no log files are written."""

    level: str


@dataclass(frozen=True)
class RateLimitConfig:
    """Per-provider request-per-minute caps plus a 429 backoff."""

    requests_per_minute: dict[str, int]
    rate_limit_backoff_seconds: int

    def rpm_for(self, provider: str) -> int:
        return self.requests_per_minute.get(provider, 5)


@dataclass(frozen=True)
class RetryConfig:
    """Generic retry policy applied to API calls."""

    max_retries: int
    backoff_seconds: int


@dataclass(frozen=True)
class Config:
    """Top-level configuration object for the entire pipeline."""

    project_name: str
    environment: str
    schedule: ScheduleConfig
    story: StoryConfig
    ai_providers: AIProvidersConfig
    tts: TTSConfig
    video: VideoConfig
    subtitles: SubtitlesConfig
    youtube: YouTubeConfig
    logging: LoggingConfig
    rate_limits: RateLimitConfig
    retry: RetryConfig
    raw: dict[str, Any] = field(repr=False)


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read and parse a YAML file, raising a clear error if it's missing."""
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path}. "
            "Copy config/config.yaml.example if you deleted it, "
            "or restore config/config.yaml."
        )
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """
    Allow select values to be overridden by environment variables so
    GitHub Actions runs can adjust behavior (e.g. test mode) without
    editing config.yaml. Only a small, explicit allowlist is supported
    to avoid surprising, hard-to-trace config drift.
    """
    env_environment = os.environ.get("STORYSHORTS_ENVIRONMENT")
    if env_environment:
        data.setdefault("project", {})["environment"] = env_environment
    return data


def load_config(path: Path | None = None) -> Config:
    """
    Load and validate configuration from YAML into a typed Config object.

    Args:
        path: Optional override path to a config YAML file. Defaults to
            config/config.yaml next to this module.

    Returns:
        A fully populated, immutable Config instance.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    data = _read_yaml(config_path)
    data = _apply_env_overrides(data)

    project = data.get("project", {})
    schedule = data["schedule"]
    story = data["story"]
    providers = data["ai_providers"]
    tts = data["tts"]
    video = data["video"]
    subtitles = data["subtitles"]
    youtube = data["youtube"]
    logging_cfg = data["logging"]
    rate_limits = data["rate_limits"]
    retry = data["retry"]

    return Config(
        project_name=project.get("name", "StoryShorts AI"),
        environment=project.get("environment", "production"),
        schedule=ScheduleConfig(
            shorts_per_day=schedule["shorts_per_day"],
        ),
        story=StoryConfig(
            min_seconds=story["min_seconds"],
            max_seconds=story["max_seconds"],
            language=story["language"],
            tone=story["tone"],
            candidates_per_run=story["candidates_per_run"],
            min_acceptable_score=story["min_acceptable_score"],
        ),
        ai_providers=AIProvidersConfig(
            fallback_order=providers["fallback_order"],
            max_retries_per_provider=providers["max_retries_per_provider"],
            retry_backoff_seconds=providers["retry_backoff_seconds"],
            gemini=ProviderModelConfig(providers["gemini"]["preferred_models"]),
            openrouter=ProviderModelConfig(providers["openrouter"]["preferred_models"]),
            groq=ProviderModelConfig(providers["groq"]["preferred_models"]),
        ),
        tts=TTSConfig(
            primary_provider=tts["primary_provider"],
            fallback_provider=tts["fallback_provider"],
            voice=tts["voice"],
            gemini_voice=tts.get("gemini_voice", "kore"),
            speaking_rate=tts["speaking_rate"],
        ),
        video=VideoConfig(
            resolution=tuple(video["resolution"]),
            fps=video["fps"],
            audio_codec=video["audio_codec"],
            video_codec=video["video_codec"],
            render_preset=video["render_preset"],
            max_duration_seconds=video["max_duration_seconds"],
            gameplay_dir=video["gameplay_dir"],
            music_dir=video["music_dir"],
            font_dir=video["font_dir"],
            avoid_repeat_gameplay=video["avoid_repeat_gameplay"],
            music_volume_db=video["music_volume_db"],
            music_fade_seconds=video["music_fade_seconds"],
        ),
        subtitles=SubtitlesConfig(
            words_per_group=subtitles["words_per_group"],
            font_size=subtitles["font_size"],
            font_color=subtitles["font_color"],
            outline_color=subtitles["outline_color"],
            highlight_color=subtitles.get("highlight_color", "yellow"),
            card_alpha=float(subtitles.get("card_alpha", 0.5)),
            card_header=subtitles.get("card_header", "u/storytime"),
        ),
        youtube=YouTubeConfig(
            visibility=youtube["visibility"],
            category_id=youtube["category_id"],
            default_language=youtube["default_language"],
            made_for_kids=youtube["made_for_kids"],
        ),
        logging=LoggingConfig(
            level=logging_cfg["level"],
        ),
        rate_limits=RateLimitConfig(
            requests_per_minute=rate_limits.get("requests_per_minute", {}),
            rate_limit_backoff_seconds=rate_limits.get("rate_limit_backoff_seconds", 30),
        ),
        retry=RetryConfig(
            max_retries=retry["max_retries"],
            backoff_seconds=retry["backoff_seconds"],
        ),
        raw=data,
    )
