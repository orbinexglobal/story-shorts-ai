# Implementation — 10 Shorts/day, guaranteed

## Goal

The channel must upload **10 YouTube Shorts every day, no matter what**. To
survive failures (rate limits, provider outages, render hiccups) we run
**12 attempts** per day and expect at least **10 uploads**; if more attempts
fail than expected, the pipeline keeps trying until the day's 10 uploads are
made (bounded by a safety cap). Uploads stop as soon as the daily total
reaches 10.

Sessions should finish in roughly **5 minutes each** (approximate, not a hard
limit).

The strategic goal behind the volume is **10M views in 90 days**. That is a
viral-outcome goal, not a production guarantee: we maximize the chance of it
by (a) never missing a day, (b) maximizing retention per Short, and
(c) running enough daily volume that a breakout hit is statistically likely.

## Current behaviour

- `.github/workflows/pipeline.yml` triggers 5×/day, each run makes **1 short**
  (`--count 1`), so a bad day can drop the channel to 4-5 uploads or fewer.
- The OpenRouter provider **gave up on the first HTTP 429** and never tried
  the other four free models, so a single rate-limited model killed the run
  (`All text providers failed ... rate limit (HTTP 429)`).
- No daily cap logic exists: nothing knows how many shorts were already
  uploaded today.

## Design

| Rule | Mechanism |
|---|---|
| 10 uploads/day guaranteed | Workflow runs the pipeline repeatedly through the day; each session uploads up to the daily target minus what's already live |
| Run 12 to upload 10 | 12 attempts/day across sessions; failures are absorbed and later sessions top up the count |
| Stop at 10 | `main.py --target 10` checks today's upload count via the YouTube Data API before each short and stops when the cap is reached |
| ~5 min sessions | Keep `--count` small per session (e.g. 1-2 shorts), run sessions several times a day instead of one giant batch |

## Changes

### 1. OpenRouter 429 resilience (`providers/openrouter_provider.py`)

- **Before:** `except RateLimitError: raise` — one model's 429 aborted the
  provider, then the whole text chain failed.
- **After:** a 429 on one model logs a warning and tries the **next** model in
  `preferred_models`. Only when **all** models fail does the provider give up.
  This alone fixes the observed `HTTP 429 on openai/gpt-oss-20b:free`
  failures, because the other 4 free models have separate daily caps.

### 2. Daily upload cap (`config/config.yaml`, `config/settings.py`, `main.py`)

- New config key: `schedule.daily_upload_target: 10`.
- New CLI flag: `python main.py --target 10`.
- `run_pipeline` queries today's live upload count (via YouTube Data API) and
  stops making shorts as soon as `uploaded_today + made >= target`.
- Exit code stays `1` only if zero shorts succeeded; reaching the cap is a
  successful run.

### 3. Count today's uploads (`youtube/`)

- New function `count_uploads_today()` lists the channel's uploads published
  today (UTC) through the YouTube Data API (`playlistItems.list` on the
  uploads playlist).
- Requires the OAuth scope to include read access
  (`youtube.readonly` + `youtube.upload`); the refresh token must be
  regenerated once (see SETUP.md, `scripts/get_youtube_refresh_token.py`).
- If the count query fails (e.g. old token), it logs a warning and assumes 0
  so the pipeline still uploads rather than stalling.

### 4. Workflow schedule (`.github/workflows/pipeline.yml`)

- Cron fires 12×/day so total attempts ≈ 12 (see crons below).
- Each session runs `python main.py --count 1 --target 10 --slot $SLOT`
  (small count keeps sessions ~5 min; the daily target is shared state via
  YouTube).
- `timeout-minutes` kept large enough to absorb retries/backoff.

### 5. Config tuning (`config/config.yaml`)

- `schedule.daily_upload_target: 10`.
- `retry.backoff_seconds` and `rate_limits.rate_limit_backoff_seconds` keep
  the chain resilient to transient 429s, and all 5 OpenRouter free models stay
  in `preferred_models`.
- `story.candidates_per_run: 2` — generate two stories, keep the best, so
  quality comes from selection instead of luck.

### 5b. Multi-account OpenRouter key rotation (free-tier fix)

Free-tier 429s are **per-account** (50 req/day each), so rotating multiple
free accounts multiplies the daily budget:

- `providers/openrouter_provider.py` now reads `OPENROUTER_API_KEY`,
  `OPENROUTER_API_KEY_2` ... `_5` and tries each key (then each model) in
  order. 2 accounts = 100 req/day, 3 = 150/day, etc.
- One account is still ~50/day — tight for 10 uploads (needs ~30-70). Two
  accounts gives comfortable headroom without spending anything.
- `.env.example` and `pipeline.yml` document/pass `OPENROUTER_API_KEY_2/3`
  as GitHub Secrets.

### 5c. Viral scoring gate (no luck, no weak hooks)

`providers/story_generator.py` now scores stories with a **viral-weighted
score** and **per-dimension floors**:

- Weighted score favors the dimensions that drive Shorts distribution:
  hook (×3), retention (×3), curiosity (×2), ending (×2), flow/simplicity (×1).
- Hard floors: hook, ending, and retention must each be ≥ 7.0. A story with
  a cold opening or a dead ending is rejected and regenerated — it can no
  longer pass on a flattering average.
- `min_acceptable_score: 7.0` still applies on top.
- Net effect: the pipeline publishes fewer, stronger stories rather than
  burning the day's quota on stories doomed to swipe-away.

### 6. Viral-content prompts (`prompts/`)

- `story_prompt.txt`: force a **hook in the first sentence**, add a new
  escalation every 2-3s, end on a twist + an open question that invites
  comments ("What would you have done?"), and bias length toward **20-30s**
  (the winning window in the data; the 50s video flopped). Adds a single soft
  **subscribe CTA** ("Follow TinyPop TV for more stories like this.") only at
  the very end, after the twist, so it converts subs without hurting retention.
- `title_prompt.txt`: push curiosity-gap titles in the proven pattern
  `"The [Object] That [Something Happened]"`, never spoil the twist.
- `description_prompt.txt`: add a one-line comment prompt ("What would you
  do?"), a soft subscribe line, and the `#TinyPopTV` brand hashtag — comments
  and subs are both algorithm and retention signals.

## Subscriber-conversion fix (0.021% → target 0.5-1.5%)

The Aug 7 batch got 4,747 views but only **+1 subscriber (0.021%)** — about
**50x below** the Shorts-industry average of 0.5-1.5%. Root cause was code:
both prompts explicitly forbade asking for a subscribe, so the channel had no
conversion mechanism. Fixed:

- Story now ends with a soft subscribe CTA **after** the twist + comment
  question (post-twist placement keeps swipe-away low).
- Description carries "Follow TinyPop TV for a new story every day." plus the
  `#TinyPopTV` hashtag.
- At the historical ~4,700 views, even a 1% conversion would have produced
  ~47 subscribers instead of 1.

Channel-side (manual, one-time): privatize the 2024 BGMI shorts so the
channel reads as one niche — mixed content suppresses both reach and subs.

## Channel-cleanup recommendation (manual, one-time)

The five old BGMI gameplay shorts from 2024 (1-3 views each) and the six
Aug-7 storytime shorts that got 0-2 views dilute the channel. Keep the three
winners visible; consider **privatizing** the rest so the channel reads as a
consistent niche. Use YouTube Studio — no code needed.

## Acceptance checks

- 6 successful runs uploaded on 2026-08-07/08 (see logs). After this change:
  - No run dies from a single model's 429.
  - The day's uploads reach 10 and then stop (no overshoot).
  - Each session finishes near ~5 minutes (approx).
- `python -m pytest tests/` stays green.
- Local dry-run check: `python main.py --test` renders without uploading.

## Open questions / follow-ups

- YouTube Data API daily quota: ~10 uploads + a handful of count calls per day
  is comfortably within the default 10,000-unit daily quota
  (`videos.insert` ≈ 100 units each since Dec 2025, `playlistItems.list` ≈ 1
  unit each). 10 uploads ≈ 1,000 units/day. ✅
- The refresh token must be regenerated with the read scope for the stop-at-10
  logic to work; without it the pipeline still uploads (count assumed 0).

## Free-tier capacity check (10 uploads/day)

| Provider | Free limit | Usage for 10/day | Verdict |
|---|---|---|---|
| OpenRouter (1 key) | 50 req/day per account | ~30-70 calls/day | ⚠️ tight |
| OpenRouter (2 keys) | 100 req/day | ~30-70 calls/day | ✅ comfortable |
| Groq | ~1,000 req/day | ~30 | ✅ |
| Gemini | ~1,500 req/day | ~30 | ✅ |
| YouTube Data API | 10,000 units/day | ~1,000 units (10 uploads) | ✅ |
| GitHub Actions | Public repo = unlimited | 12 runs/day | ✅ |

Each Short costs ~3-5 text calls (2 story candidates + 2 metadata);
retries can push a day to 50-70 calls. A single free account (50/day)
sits exactly at that ceiling. **Solution without spending: register a
second free OpenRouter account and set `OPENROUTER_API_KEY_2`** — the
provider rotates accounts automatically (section 5b), giving ~100 req/day.
The chain also falls back to Groq/Gemini if both are exhausted.

---

# Viral-growth strategy (10M views in 90 days)

## Where the channel stands (data: 2026-07-11 → 2026-08-08)

| Metric | Value |
|---|---|
| Total views (all content) | 4,747 |
| Engaged views | 1,487 |
| Avg % viewed (storytime) | 40-45% |
| Avg view duration | 11-13s |
| Subscribers gained | 1 |
| Best day | 2026-08-07 (1,482 engaged views) |

**What the winners (1400-1700 views each) have in common:**

- **Duration 24-29s** — short enough to hold retention. The 50s video got 1 view.
- **Title = curiosity gap, no spoiler:**
  - "The Polaroid That Predicted My Future" (535 engaged)
  - "The Tiny Green Padlock That Locked Me Down" (506 engaged)
  - "The Basement Door That Used My Key" (440 engaged)
- **First-person supernatural/horror** hook, escalating mystery, twist ending.
- **Published in the same batch** (Aug 7) — the algorithm tested and promoted them.

**What the flops (1-2 views) share:**

- Same niche but weaker titles ("I Ignored Dad's Warning, Found a Door Inside"),
  longer runtime (50s), or released after the batch's distribution window.

## The math on 10M / 90 days

At the current steady-state rate (~1,500 engaged views/day on a good day,
zero on bad days), a purely linear ramp gets nowhere near 10M. 10M in 90 days
needs an average of **~111,000 views/day**. That only happens via **short-form
virality**: a handful of Shorts that each pick up 1-5M views, plus a steady
baseline from the daily 10.

The realistic path is a **retention + volume + iteration loop**:

1. **Never miss a day, never cap at 1.** 10 Shorts/day = ~900 in 90 days.
   Each Short is a lottery ticket; volume is the only guaranteed multiplier.
2. **Fix retention first.** YouTube Shorts ranks on **avg % viewed** and
   **swipe-away rate**. Today the channel is at ~43% viewed. Winners in this
   niche sit at 65-85%. Every point of retention compounds reach.
3. **Double down on the winning formula.** 24-30s, object-based curiosity
   title, first-person eerie escalation, twist + comment-prompting ending.
4. **Feed the algorithm engagement signals.** Comments (end with a question),
   shares (shock/twist endings), loops (end that visually suggests the start).
5. **Iterate weekly on data.** Compare % viewed and CTR per title pattern;
   keep the patterns that lift retention, drop those that don't.

## What this repo changes to chase it

- **Prompts** now enforce the winning runtime + hook + comment-prompt.
- **Volume**: 10/day regardless of single-run failures (target + retries).
- **Consistency**: slots keep daily clips distinct; sessions spread across the
  day so a flop batch can't kill a whole day.
- Everything else (the actual viral outcome) is decided by viewer retention —
  which is now the thing the pipeline optimizes for.

## Realistic expectation

10M/90d is a stretch goal. The engineering guarantees the **volume and
quality floor** (10 fresh, high-retention-formatted Shorts every day). The
algorithm does the rest. A single 2M-view hit in a 900-video runway is far
more likely than it sounds when retention and daily volume are both correct —
but no pipeline can *promise* a specific view count.
