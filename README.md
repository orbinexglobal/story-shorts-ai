# StoryShorts AI

An automation pipeline that takes a source video, cuts a segment,
writes a first-person Reddit-style story over it, adds a title,
word-synced captions and a narrated voice track, then renders and
uploads the result as a YouTube Short. One run makes **5 Shorts**
(the default daily batch) and uploads them — that's it.

## Quick start

```bash
pip install -r requirements.txt
python main.py --test     # makes 5 Shorts, renders them to output/, no upload
python main.py            # makes 5 Shorts and uploads them to YouTube
python main.py --count 3  # make 3 Shorts instead of the default 5
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

- One command makes the whole daily batch: `schedule.shorts_per_day`
  (default 5) in `config/config.yaml`
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

`.github/workflows/pipeline.yml` runs the pipeline once a day (cron
`30 8 * * *`); each run makes and uploads the daily batch of 5 Shorts.
Set the repo secrets listed in the workflow for automated deployment.

## Testing

```bash
python -m pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).
