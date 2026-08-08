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
    python main.py                # 1 Short, uploaded to YouTube (default batch)
    python main.py --test         # 1 Short rendered, upload skipped
    python main.py --count 3      # 3 Shorts instead of the default
    python main.py --slot 2       # start from slot 2 of the day's clip shuffle
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
from utils.daily_count import read_daily_count, record_daily_count
from youtube.uploader import count_uploads_today, upload_video

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StoryShorts AI — take a video, cut it, narrate, caption, upload."
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="How many Shorts to make this run. Defaults to schedule.shorts_per_day.",
    )
    parser.add_argument(
        "--slot", type=int, default=0,
        help="Slot in the day's clip shuffle (0-6). Each scheduled run uses a "
             "different slot so the day's uploads rotate through distinct videos.",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Render the Shorts but skip the YouTube upload step.",
    )
    parser.add_argument(
        "--target", type=int, default=None,
        help="Stop once this many Shorts are live today (defaults to "
             "schedule.daily_upload_target). Requires read scope on the "
             "YouTube token; falls back to no cap if the count can't be read.",
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
    slot: int,
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

    clip = select_gameplay(cfg, needed_duration=tts_result.duration, slot=slot)
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


def run_pipeline(count: int, test_mode: bool, slot: int = 0, target: int | None = None) -> int:
    _load_dotenv()

    cfg = load_config()
    configure_logging(cfg)

    count = count or cfg.schedule.shorts_per_day
    target = target if target is not None else cfg.schedule.daily_upload_target
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    text_provider = TextProviderChain(cfg)
    tts_provider = TTSProviderChain(cfg)

    uploaded_today = 0
    if not test_mode and target:
        uploaded_today = _daily_uploaded_count(cfg, target)
        logger.info("Already uploaded today: %d/%d", uploaded_today, target)

    made = 0
    for i in range(1, count + 1):
        if target and uploaded_today + made >= target:
            logger.info(
                "Daily target reached (%d/%d); stopping this run.", uploaded_today + made, target
            )
            break
        try:
            make_short(i, count, text_provider, tts_provider, cfg, output_dir, test_mode, slot)
            made += 1
            if not test_mode and target:
                record_daily_count(uploaded_today + made)
        except (StoryQualityError, ProviderError, NoGameplayAssetsError,
                RenderError, ValidationError) as exc:
            logger.error("Short %d failed: %s", i, exc)

    logger.info("Done: %d/%d Shorts in %s", made, count, output_dir)
    return 0 if made > 0 else 1


def _daily_uploaded_count(cfg: Config, target: int) -> int:
    """
    Return how many Shorts are live today, for enforcing the daily cap.

    Prefers the YouTube Data API (accurate source of truth). If that fails
    (e.g. upload-only token without read scope), falls back to the committed
    state file so the cap still works instead of assuming 0 and overshooting.
    Returns `target` (i.e. cap reached) if the count can't be determined at
    all, so we never upload more than the daily target.
    """
    try:
        count = count_uploads_today(cfg)
        logger.info("Daily count from YouTube API: %d", count)
        record_daily_count(count)
        return count
    except ProviderError as exc:
        logger.warning(
            "YouTube API count failed (%s); using state file fallback.", exc,
        )
    try:
        count = read_daily_count()
        logger.info("Daily count from state file: %d", count)
        return count
    except Exception as exc:  # noqa: BLE001 - cap must not be bypassable
        logger.warning("State file unreadable (%s); assuming cap reached.", exc)
        return target


def main() -> None:
    args = parse_args()
    sys.exit(run_pipeline(
        count=args.count, test_mode=args.test, slot=args.slot, target=args.target,
    ))


if __name__ == "__main__":
    main()
