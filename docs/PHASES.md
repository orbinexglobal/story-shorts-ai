# Build history

This was originally scoped as a phase-by-phase build with a stop for
review after each phase. At the user's request, all phases were
completed together in one delivery. This file is kept as a record of
what was built and where to look for each part.

## Phase 1 — Skeleton ✅

- Folder structure
- `config/config.yaml` — every tunable value
- `config/settings.py` — typed, validated config loader
- `config/logging_setup.py` — console + one-JSON-file-per-day logging
- `main.py` — CLI, pipeline shape
- `requirements.txt`, `.gitignore`, `LICENSE`, `README.md`

## Phase 2 — AI providers + story generation ✅

- `providers/gemini_provider.py`, `openrouter_provider.py`,
  `groq_provider.py` — one client per provider, common `TextProvider`
  interface
- `providers/text_chain.py` — fallback chain with per-provider retries,
  skips any provider whose API key isn't set
- `providers/story_generator.py` — N candidates, self-scored across 6
  dimensions, best kept, run aborted below the quality threshold
- `providers/metadata_generator.py` — title/description/hashtags
- `prompts/` — templates for all three

## Phase 3 — Audio + video pipeline ✅

- `providers/gemini_tts_provider.py`, `edge_tts_provider.py`,
  `providers/tts_chain.py` — TTS fallback chain
- `video/gameplay_selector.py` — random pick, no-repeat-in-a-row,
  random valid start timestamp
- `video/music_selector.py` — random background track
- `video/subtitles.py` — ASS generation, approximate word-level sync
- `video/renderer.py` — single-pass ffmpeg render
- `video/validator.py` — duration/resolution/stream checks pre-upload

## Phase 4 — Upload + scheduling infrastructure ✅

- `youtube/auth.py`, `youtube/uploader.py` — OAuth + Data API upload
- `scripts/get_youtube_refresh_token.py` — one-time local OAuth helper
- `.github/workflows/pipeline.yml` — scheduled GitHub Actions workflow
- `utils/resource_manager.py` — self-tracked Actions runtime budget,
  reduces upload cadence as the free-tier minute budget runs low

## Phase 5 — Polish ✅

- `SETUP.md` — full walkthrough (Python, ffmpeg, GitHub, all API keys,
  YouTube OAuth end-to-end)
- `utils/healthcheck.py` — pre-flight checks with plain-English errors
  instead of mid-pipeline crashes
- `main.py --offline` — full pipeline smoke test with mock providers
  and synthetic assets; requires no credentials, no network, no real
  gameplay/music files
- `tests/` — starter test suite

## Known limitations (by design, documented rather than hidden)

- Subtitle timing is approximate (even word spacing across the
  measured audio duration), since none of the integrated providers
  return word-level timestamps.
- The GitHub Actions runtime budget is self-tracked from each run's
  wall-clock duration, not read from GitHub's billing API (which isn't
  reliably reachable with a simple repo token). Treat it as a guide,
  not a billing-accurate number.
- Gemini TTS's exact response shape can shift between model versions;
  any failure there is caught and the pipeline falls back to Edge TTS
  automatically rather than crashing.
