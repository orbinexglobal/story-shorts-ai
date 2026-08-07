# StoryShorts AI — Master Implementation Plan & System Architecture

This document provides a comprehensive, production-ready specification and technical blueprint for **StoryShorts AI**, an autonomous, zero-operating-cost video generation and publishing engine. The system crafts original, family-friendly short stories, generates narration and word-synced subtitles, composites narration over gameplay clips and background audio, and uploads vertical YouTube Shorts on an automated schedule.

---

## 1. Executive Summary & Core Objectives

- **Target Platform**: YouTube Shorts (1080x1920 vertical video, < 60s duration).
- **Operating Cost**: **$0 / month** — leverages free AI model quotas (Gemini, OpenRouter, Groq), free TTS (Edge TTS / Gemini TTS), local FFmpeg processing, and GitHub Actions runner minutes.
- **Monetization & Partner Program Compliance**: Focuses on high-retention, original story candidate scoring rather than repetitive template rendering or raw stock asset looping.
- **Resilience**: Features multi-tier fallback chains for both Text LLMs and Text-to-Speech engines, automated output validation, and runtime budget tracking.

---

## 2. System Architecture & End-to-End Workflow

The pipeline operates as a modular, linear sequence guarded by health checks and quality validation gates.

```
                    +------------------------------------+
                    |   GitHub Actions Cron / Manual     |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  Pre-flight Healthcheck & Budget   |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  AI Story Generator (Candidate N)  |
                    |  Multi-Dimensional Quality Scoring |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  Metadata Generator (Title & Desc) |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  TTS Engine (Voice Synthesis)      |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  Asset Selector (Gameplay + Music) |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  ASS Subtitle Generator            |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  FFmpeg Single-Pass Renderer       |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  FFprobe Output Validator          |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  YouTube Data API v3 Uploader      |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  Logger & Resource Budget Tracker  |
                    +------------------------------------+
```

---

## 3. Directory & Module Structure

```
story-shorts-ai/
├── main.py                          # Primary CLI & execution orchestrator
├── config/
│   ├── config.yaml                  # Unified project configuration parameters
│   ├── settings.py                  # Dataclass config loader & validator
│   └── logging_setup.py             # Console & daily JSONL file logger
├── providers/
│   ├── base.py                      # Abstract base classes for Text & TTS providers
│   ├── gemini_provider.py           # Google Gemini API implementation
│   ├── openrouter_provider.py       # OpenRouter multi-model implementation
│   ├── groq_provider.py             # Groq LLaMA implementation
│   ├── text_chain.py                # Failover orchestrator for Text LLMs
│   ├── gemini_tts_provider.py       # Gemini Voice synthesis provider
│   ├── edge_tts_provider.py         # Microsoft Edge TTS provider (zero API key)
│   ├── tts_chain.py                 # Failover orchestrator for TTS providers
│   ├── story_generator.py           # Multi-candidate generation & scoring engine
│   ├── metadata_generator.py        # Optimized Title, Description, and Hashtags
│   ├── offline_provider.py          # Offline mock Text provider
│   └── offline_tts_provider.py      # Offline mock Silent TTS provider
├── video/
│   ├── gameplay_selector.py         # Gameplay clip picker (no-repeat history)
│   ├── music_selector.py            # Royalty-free music track picker
│   ├── subtitles.py                 # ASS subtitle generator with word grouping
│   ├── renderer.py                  # Single-pass FFmpeg video/audio/filter graph
│   └── validator.py                 # Post-render FFprobe verification suite
├── youtube/
│   ├── auth.py                      # OAuth2 flow & token refresh helper
│   └── uploader.py                  # YouTube Data API v3 video uploader
├── utils/
│   ├── healthcheck.py               # Pre-flight environment & API key verifier
│   ├── resource_manager.py          # GitHub Actions runtime budget calculator
│   └── json_extract.py              # Robust JSON parser for LLM outputs
├── prompts/
│   ├── story_prompt.txt             # Structured story generation & scoring prompt
│   ├── title_prompt.txt             # Title optimization prompt
│   └── description_prompt.txt       # Description and tags prompt
├── scripts/
│   └── get_youtube_refresh_token.py # One-time helper to obtain OAuth refresh token
├── assets/
│   ├── gameplay/                    # Vertical/Landscape gameplay clips
│   ├── music/                       # Background music audio files (.mp3, .wav)
│   └── fonts/                       # Fonts for subtitle rendering (.ttf, .otf)
├── docs/
│   └── PHASES.md                    # Detailed roadmap & development history
├── tests/                           # Pytest test suite
│   ├── test_config.py
│   ├── test_json_extract.py
│   └── test_story_generator.py
├── .github/workflows/
│   └── pipeline.yml                 # GitHub Actions CRON automation
├── requirements.txt                 # Project dependencies
└── SETUP.md                         # Detailed step-by-step setup documentation
```

---

## 4. Subsystem Deep-Dives

### 4.1 Configuration Management (`config/`)
- Centralized in `config/config.yaml`.
- Parsed into strongly-typed Python dataclasses via `config/settings.py`.
- **Key Parameters**:
  - `story`: `min_seconds` (20), `max_seconds` (30), `candidates_per_run` (3), `min_acceptable_score` (7.0).
  - `ai_providers.fallback_order`: `["gemini", "openrouter", "groq"]`.
  - `tts`: `primary_provider: "gemini"`, `fallback_provider: "edge_tts"`, `voice: "en-US-AriaNeural"`.
  - `video`: `resolution: [1080, 1920]`, `fps: 30`, `video_codec: "h264"`, `audio_codec: "aac"`, `music_volume_db: -18`.
  - `subtitles`: `words_per_group: 2`, `font_size: 90`, `font_color: "white"`, `outline_color: "black"`.

### 4.2 Multi-Candidate Story Generation & Quality Filter (`providers/story_generator.py`)
To avoid low-quality AI outputs, the pipeline:
1. Requests `candidates_per_run` (default: 3) independent stories from the active Text LLM chain.
2. Prompts the LLM to score each story across 6 dimensions (scale 1–10):
   - `hook_score`: Initial 3-second retention efficiency.
   - `curiosity_score`: Story arc tension.
   - `emotional_flow_score`: Pacing and satisfaction.
   - `ending_score`: Twist or resolution quality.
   - `simplicity_score`: Vocabulary clarity for children/general audiences.
   - `retention_score`: Likelihood of rewatch.
3. Computes `overall_score` as the arithmetic mean of all 6 sub-scores.
4. **Quality Gate**: Selects the highest-scoring candidate. If `best.overall_score < min_acceptable_score` (7.0), the run is aborted immediately to protect channel reputation.

### 4.3 Text & TTS Provider Fallback Chains
- **Text LLM Chain (`providers/text_chain.py`)**:
  - Tries **Gemini** (`gemini-2.5-flash`, `gemini-2.0-flash`).
  - On failure/missing key, fails over to **OpenRouter** (`gpt-oss-20b:free`, `qwen3-235b-a22b:free`, `deepseek-chat-v3:free`, `gemma-3-27b-it:free`).
  - On failure, fails over to **Groq** (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`).
- **TTS Chain (`providers/tts_chain.py`)**:
  - Tries **Gemini TTS** -> Fails over seamlessly to **Edge TTS** (Microsoft Edge neural voice engine, requiring no API key).

### 4.4 Subtitle Generator (`video/subtitles.py`)
- Generates Advanced SubStation Alpha (`.ass`) format subtitle files.
- Splits narration text into chunks of `words_per_group` (default: 2 words).
- Calculates proportional start/end timestamps based on total narration duration.
- Applies vertical offset (`MarginV=280`), centered alignment (`Alignment=2`), bold font styling, and high-contrast outline borders.

### 4.5 FFmpeg Single-Pass Rendering Engine (`video/renderer.py`)
Executes a single, non-destructive FFmpeg command to composite video, narration, music, and burned subtitles without intermediate encoding steps:

```bash
ffmpeg -y \
  -i <gameplay_clip> \
  -i <narration_wav> \
  -stream_loop -1 -i <background_music> \
  -filter_complex "\
    [0:v]trim=start=<start_s>:duration=<dur>,setpts=PTS-STARTPTS,\
         scale=1080:1920:force_original_aspect_ratio=increase,\
         crop=1080:1920,ass='<subtitles_ass>'[vout];\
    [2:a]volume=-18dB,afade=t=in:st=0:d=2,afade=t=out:st=<fade_out_start>:d=2[music];\
    [1:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
  -map "[vout]" -map "[aout]" \
  -t <dur> -r 30 -c:v libx264 -pix_fmt yuv420p -c:a aac <output_mp4>
```

### 4.6 Output Validation Suite (`video/validator.py`)
Before attempting upload, the output file undergoes automated inspection via `ffprobe`:
1. Verifies non-zero byte size (> 100 KB).
2. Verifies presence of exactly one video stream (`h264`) and one audio stream (`aac`).
3. Confirms resolution is exactly `1080x1920`.
4. Confirms duration matches narration length within a ±1.5s tolerance and does not exceed 60 seconds.

### 4.7 YouTube Data API Uploader (`youtube/uploader.py`)
- Authenticates using OAuth2 client credentials and a saved refresh token.
- Uses standard YouTube Data API v3 (`youtube.videos.insert`).
- Sets metadata: title, full description with hashtags, category ID (`24` - Entertainment), privacy status (`public`), and `madeForKids: false`.

### 4.8 Resource & Runtime Budget Tracking (`utils/resource_manager.py`)
- Tracks monthly execution minutes against GitHub Actions' free allowance (2000 minutes/month).
- Maintains state in local runtime records.
- **Throttling Logic**:
  - `Warning` threshold (80% used): Reduces upload frequency to `reduced_uploads_per_day` (5).
  - `Critical` threshold (95% used): Aborts scheduled runs before asset rendering/upload to avoid runner quota exhaustion.

---

## 5. Execution Modes & CLI Reference

| Mode | Command | Description |
| :--- | :--- | :--- |
| **Offline Smoke Test** | `python main.py --offline` | Uses synthetic video/audio & offline mock LLMs. Requires zero API keys or network. Implies `--test`. |
| **Test Mode** | `python main.py --test` | Executes full pipeline with real AI APIs & FFmpeg rendering, but skips YouTube upload. |
| **Production** | `python main.py` | Full autonomous execution including YouTube Data API upload. |

---

## 6. GitHub Actions Deployment & Secrets Setup

Scheduled execution is managed via `.github/workflows/pipeline.yml`, configured with 6 daily CRON dispatches:

```yaml
on:
  schedule:
    - cron: "7 8 * * *"
    - cron: "14 11 * * *"
    - cron: "23 14 * * *"
    - cron: "5 17 * * *"
    - cron: "18 20 * * *"
    - cron: "11 22 * * *"
  workflow_dispatch: {}
```

### Required GitHub Secrets
- `GEMINI_API_KEY`: API key from Google AI Studio.
- `OPENROUTER_API_KEY`: API key from OpenRouter.
- `GROQ_API_KEY`: API key from Groq Cloud.
- `YOUTUBE_CLIENT_ID`: Google OAuth2 Client ID.
- `YOUTUBE_CLIENT_SECRET`: Google OAuth2 Client Secret.
- `YOUTUBE_REFRESH_TOKEN`: OAuth2 Refresh Token (generated via `scripts/get_youtube_refresh_token.py`).

---

## 7. Future Scalability & Feature Roadmap

1. **Character Memory & Narrative Persistence**: Maintain recurring character entities (e.g., *Blue Dino*, *Tiny Robot*) across episodes to foster viewer familiarity and subscriber loyalty.
2. **Dynamic AI Image Scene Generation**: Transition from loopable background gameplay footage to multi-scene AI-generated visual panels using Flux / SDXL models.
3. **Analytics Feedback Loop**: Periodically query YouTube Analytics API to evaluate swipe-away rates and audience retention, automatically tuning story prompts and character selection.
4. **Thumbnail Generation**: Automatically crop and overlay title text on a high-scoring video frame for custom thumbnail generation.
