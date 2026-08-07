"""
StoryShorts AI — take a video, cut it, narrate a story over it, upload.

For each of `count` Shorts (default 5 = one day's batch):
    1. cut      — pick a source video and cut a random segment from it
    2. story    — AI writes a first-person Reddit-style story
    3. title    — AI writes the title, description and hashtags
    4. voice    — TTS synthesizes the narration
    5. caption  — word-synced subtitle captions are generated
    6. render   — FFmpeg burns the captions over the video segment
    7. upload   — the Short is published to YouTube

Usage:
    python main.py            # 5 Shorts, uploaded to YouTube
    python main.py --test     # 5 Shorts rendered, upload skipped
    python main.py --count 3  # 3 Shorts instead of the default
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from config.logging_setup import configure_logging, get_logger
from config.settings import Config, load_config
from providers.base import ProviderError
from providers.metadata_generator import generate_metadata
from providers.story_generator import StoryQualityError, generate_story
from providers.text_chain import TextProviderChain
from providers.tts_chain import TTSProviderChain
from video.gameplay_selector import NoGameplayAssetsError, select_gameplay
from video.music_selector import select_music
from video.renderer import RenderError, render_video
from video.subtitles import generate_ass
from video.validator import ValidationError, validate_output
from youtube.uploader import upload_video

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StoryShorts AI — take a video, cut it, narrate, caption, upload."
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="How many Shorts to make this run. Defaults to 5 (one day's batch).",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Render the Shorts but skip the YouTube upload step.",
    )
    return parser.parse_args(argv)


def make_short(
    index: int,
    total: int,
    text_provider,
    tts_provider,
    cfg: Config,
    output_dir: Path,
    test_mode: bool,
) -> None:
    """Make a single Short: story -> title -> voice -> caption -> cut -> render -> upload."""
    logger.info("=== Short %d/%d ===", index, total)

    story = generate_story(text_provider, cfg)
    logger.info("Story (score=%.1f): %s", story.overall_score, story.text)

    metadata = generate_metadata(text_provider, story.text)
    logger.info("Title: %s", metadata.title)

    narration_path = output_dir / f"short_{index:02d}_narration.wav"
    tts_result = tts_provider.synthesize(story.text, out_path=str(narration_path))
    logger.info("Narration duration: %.1fs", tts_result.duration)

    clip = select_gameplay(cfg, needed_duration=tts_result.duration)
    music_path = select_music(cfg)
    logger.info("Video: %s (cut from %.1fs)  Music: %s", clip.path.name, clip.start_seconds, music_path)

    ass_path = generate_ass(
        story.text, tts_result.duration, tts_result.word_timings,
        cfg, output_dir / f"short_{index:02d}_subtitles.ass",
    )

    output_path = output_dir / f"short_{index:02d}.mp4"
    render_video(
        gameplay_path=clip.path, gameplay_start=clip.start_seconds,
        duration=tts_result.duration, narration_path=narration_path,
        music_path=music_path, ass_path=ass_path, cfg=cfg, out_path=output_path,
    )
    validate_output(output_path, cfg, expected_duration=tts_result.duration)
    logger.info("Rendered + validated: %s", output_path)

    if test_mode:
        logger.info("Test mode: upload skipped for this Short.")
        return

    video_id = upload_video(
        output_path, title=metadata.title,
        description=metadata.full_description,
        tags=[h.lstrip("#") for h in metadata.hashtags],
        cfg=cfg,
    )
    logger.info("Uploaded: https://youtube.com/shorts/%s", video_id)


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE pairs from a .env file into the environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def run_pipeline(count: int, test_mode: bool) -> int:
    _load_dotenv()

    cfg = load_config()
    configure_logging(cfg)

    count = count or cfg.schedule.shorts_per_day
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    text_provider = TextProviderChain(cfg)
    tts_provider = TTSProviderChain(cfg)

    made = 0
    for i in range(1, count + 1):
        try:
            make_short(i, count, text_provider, tts_provider, cfg, output_dir, test_mode)
            made += 1
        except (StoryQualityError, ProviderError, NoGameplayAssetsError,
                RenderError, ValidationError) as exc:
            logger.error("Short %d failed: %s", i, exc)

    logger.info("Done: %d/%d Shorts in %s", made, count, output_dir)
    return 0 if made > 0 else 1


def main() -> None:
    args = parse_args()
    sys.exit(run_pipeline(count=args.count, test_mode=args.test))


if __name__ == "__main__":
    main()
