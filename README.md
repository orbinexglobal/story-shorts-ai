# StoryShorts AI

An automation pipeline that takes a source video, cuts a segment,
writes a first-person Reddit-style story over it, adds a title,
word-synced captions and a narrated voice track, then renders and
uploads the result as a YouTube Short. Each run makes **1 Short** and
uploads it; GitHub Actions triggers the pipeline **12 times a day**,
weighted toward Indian prime hours (7-11 PM IST is the strongest window
for Indian gaming/entertainment Shorts). Evening sessions are spaced
45-60 minutes apart so each Short gets its own algorithm test pool
instead of being throttled by a same-hour batch dump. A final catch-up
run tops the day up to the 10-video cap.

## Quick start

```bash
pip install -r requirements.txt
python main.py --test     # makes 1 Short, renders it to output/, no upload
python main.py            # makes 1 Short and uploads it to YouTube
python main.py --count 3  # make 3 Shorts instead of the default
python main.py --slot 2   # start from slot 2 of the day's clip shuffle
```

Credentials are read from a local `.env` file (see SETUP.md for how to
create it): `OPENROUTER_API_KEY` (text AI) and the YouTube OAuth vars.

## How one Short is made

1. **cut** — a random segment is picked from one of your source videos
2. **story** — an AI writes a first-person story and self-scores it;
   unparseable, non-Latin-garbage, or low-scoring outputs are retried
3. **title** — an AI writes the title, description and hashtags
4. **voice** — Edge TTS synthesizes the narration (no API key needed)
5. **caption** — word-synced subtitle captions are generated
6. **render** — one FFmpeg pass burns the captions over the video
7. **upload** — the Short is published to YouTube

## Features

- One command makes one Short: `schedule.shorts_per_day` (default 1)
  in `config/config.yaml`
- Gameplay clips rotate daily with no fixed pattern — each scheduled
  upload (`--slot`) starts at a different position in a date-seeded
  shuffle, so the 7 videos are used once each before repeating
- AI text fallback chain (OpenRouter → Groq → Gemini) — if one
  provider or free model dies, the next is tried automatically
- TTS fallback chain (Edge TTS → Gemini TTS; Edge TTS needs no key)
- Garbage/quality filtering: non-Latin tokenizer junk and weak stories
  are discarded and regenerated before anything is published
- Single-pass FFmpeg render + automated output validation before upload
- YouTube Data API upload with configurable visibility
- `--test` mode renders without uploading; renders are kept in `output/`

## Folder structure

```
story-shorts-ai/
├── .github/workflows/pipeline.yml   # one scheduled GitHub Actions run/day
├── config/               # config.yaml + typed settings loader + logging
├── providers/            # AI text + TTS providers, fallback chains,
│                          # story + metadata generation
├── video/                 # video-cut, subtitles, render, validation
├── youtube/                # OAuth credentials + Data API upload
├── utils/                   # JSON extraction, rate limiting
├── prompts/                  # story/title/description prompt templates
├── scripts/                   # one-time YouTube refresh-token helper
├── assets/
│   ├── gameplay/          # your source videos (cut into Shorts)
│   ├── music/               # optional background music
│   └── fonts/                 # subtitle fonts
├── output/                      # rendered MP4s, kept as a local copy
├── tests/
├── main.py                        # entry point (default / --test / --count)
├── requirements.txt
└── config/config.yaml              # every tunable value lives here
```

## Configuration

Everything tunable — shorts per day, voice, subtitle size, story length,
video resolution, provider fallback order, quality threshold — lives in
[`config/config.yaml`](config/config.yaml). Application code reads it
through `config.settings.load_config()`; nothing is hardcoded elsewhere.

## GitHub Actions

`.github/workflows/pipeline.yml` runs the pipeline 12 times a day
(cron UTC, weighted toward Indian peak hours 7-11 PM IST); each run makes
and uploads up to one Short, then stops once the 10/day cap is reached,
with a final catch-up run to top up to exactly 10. Set the repo secrets
listed in the workflow for automated deployment.

## Testing

```bash
python -m pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).
