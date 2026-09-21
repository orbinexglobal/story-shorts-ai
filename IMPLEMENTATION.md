# Implementation — consistency + retention first (1-2 Shorts/day)

## Goal

The channel uploads **1-2 YouTube Shorts every day, no matter what**, and
every Short is engineered for high retention. This is a deliberate reversal
of the earlier "10 Shorts/day lottery-ticket" plan: the Sep 2026 analytics
export (`analytics/2026-09-21-export/`) showed that bumping ~10/day drained
the algorithm's test pools — the only videos that ever got reach were the 3
launched *before* the flood, and every Short in the flood got 1-300 views.

The strategic goal is **long-term audience growth**. We maximise the chance of
it by (a) never missing a day, (b) maximizing retention % per Short (14-20s
runtimes so ~10s of watch time reads as 60-70% instead of ~40%), and
(c) keeping cadence low enough that every upload gets a fair test pool.

## Current behaviour

- `.github/workflows/pipeline.yml` triggers 12×/day, each run makes **1 short**
  (`--count 1`), and the first 1-2 sessions that succeed each day do the
  upload; the rest exit early once the daily target of **2** is reached.
- The OpenRouter provider discovers live free models at startup, rotates
  across multiple API keys, and sinks dead/rate-limited models with process
  -wide cooldowns — a single model or key failure can't kill a run.
- Metadata (title + description + hashtags) is generated in one API call.
- `main.py --target 2` checks today's upload count via the YouTube Data API
  before each short and stops when the cap is reached.

## Design

| Rule | Mechanism |
|---|---|
| 1-2 uploads/day guaranteed | Workflow runs 12 sessions spread across the day; each session uploads up to the daily target minus what's already live |
| Low cadence, spaced | `main.py --target 2` caps each day at 2; sessions are 45-60 min apart so a flood never happens |
| ~5 min sessions | Keep `--count` small per session (1 short), run sessions several times a day instead of one giant batch |

## Changes

### 1. OpenRouter 429 resilience (`providers/openrouter_provider.py`)

- **Before:** `except RateLimitError: raise` — one model's 429 aborted the
  provider, then the whole text chain failed.
- **After:** a 429 on one model logs a warning and tries the **next** model in
  `preferred_models`. Only when **all** models fail does the provider give up.
  This alone fixes the observed `HTTP 429 on openai/gpt-oss-20b:free`
  failures, because the other 4 free models have separate daily caps.

### 2. Daily upload cap (`config/config.yaml`, `config/settings.py`, `main.py`)

- New config key: `schedule.daily_upload_target: 2`.
- New CLI flag: `python main.py --target 2`.
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
- Each session runs `python main.py --count 1 --target 2 --slot $SLOT`
  (small count keeps sessions ~5 min; the daily target is shared state via
  YouTube); only the first 1-2 sessions that succeed each day actually upload.
- `timeout-minutes` kept large enough to absorb retries/backoff.

### 5. Config tuning (`config/config.yaml`)

- `schedule.daily_upload_target: 2` — deliberately low (cadence, not volume,
  is what earns reach; see the Sep 2026 export analysis).
- `story.min_seconds: 14`, `story.max_seconds: 20` — the retention window. A
  ~16s narration at ~60-70% retention outperforms a 28s one at ~43%.
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
- One account is still ~50/day — tight for heavy days; two
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

- `story_prompt.txt`: force a **hook in the first 2 seconds** (first sentence
  carries the strangest image), a new escalation every 2-3s, 32-44 words (the
  Aug 21 run proved the model ignores a bare "HARD LIMIT", so `story_generator`
  now enforces `min_words`/`max_words` in code and regenerates anything out of
  window), a **re-read twist ending** (engineered to trigger replays) + an open
  question that invites comments ("What would you have done?"), all inside a
  **14-19s retention window** (a sub-20s Short at ~60-70% retention scales;
  a 28s Short at ~43% caps out ~1.5-2k). Adds a single soft **subscribe CTA**
  ("Follow TinyPop TV for more stories like this.") only at the very end,
  after the twist, so it converts subs without hurting retention.
- `metadata_prompt.txt`: one call that yields 5 curiosity-gap titles in the
  proven pattern `"The [Object] That [Something Happened]"` (never spoiling
  the twist), a one-line comment prompt ("What would you do?"), a soft
  subscribe line, and the `#TinyPopTV` brand hashtag — comments and subs are
  both algorithm and retention signals. Title length and ALL-CAPS rules are
  enforced in code (`_pick_best_title`), not left to the model.

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

### 7. Saga mode — serialized stories that manufacture subscriptions

CTA-based conversion caps out because a one-off Short gives a viewer no reason
to *stay*. `utils/saga_state.py` + `story.saga` in config turn the feed into
serialized storytelling instead:

- Every Short is **Part N** of a saga (titles get a `(Part N)` suffix, the
  description gets a deterministic "Part N+1 drops tomorrow — follow so you
  don't miss the ending." line).
- `build_saga_context()` injects a continuation block into the story prompt:
  Part 1 ends on a hard cliffhanger; Parts 2..N continue the exact same plot
  (the previous narration is fed back for continuity); the final part resolves
  completely.
- `state/saga_state.json` persists the chain between GitHub Actions runs
  (committed alongside `daily_upload_count.json`). The state only advances
  **after a Short truly uploads**, never in test mode.
- `story.saga.parts_per_saga: 3` (0 = perpetual series that never resolves).
- Net effect: viewers must subscribe to catch the ending — subscription
  becomes *necessary* rather than requested, which is the strongest known
  subscriber mechanic for story formats.

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

# Viral-growth strategy

## Where the channel stands (data: 2025-09-21 → 2026-09-21, full year)

See `analytics/2026-09-21-export/`. The year totals:
| Metric | Value |
|---|---|
| Total views | 10,543 (6 gameplay 2024, 79 story Shorts Aug 2026) |
| Avg % viewed (winners) | ~40-45% |
| Avg view duration | 10-11s |
| Subscribers gained | +5 (−0); channel at 3 |
| Videos > 1,000 views | 3 (max 1,795) |
| Unique reach | 7,993 |

**What the winners (1.4-1.8k views each) have in common:**

- **Launched on day one (Aug 7), before the daily dump started.** They got a
  real test pool; everything uploaded afterwards got 1-300 views.
- **Title = curiosity gap, no spoiler:**
  - "The Polaroid That Predicted My Future" (1,394)
  - "The Tiny Green Padlock That Locked Me Down" (1,739)
  - "The Basement Door That Used My Key" (1,795)
- First-person supernatural/mystery hook, escalating tension, twist ending.
- Avg % viewed ~40-45% — good enough to win a test pool, too low to escape it.

**Two findings that reshaped the strategy:**

1. **The 10/day dump throttled the channel.** ~79 Shorts were pushed in ~10
   days. YouTube gives each Short a small test pool on publish; when 10 land
   the same day they cannibalise each other and none can surface. The correct
   play is *fewer, spaced* uploads so every Short gets a fair test.
2. **Retention ~40% caps a Short at ~1.5-2k.** Shorts distribution scales on
   **avg % viewed** and **swipe-away rate**; the escape threshold is roughly
   **65%+**. At ~40%, even the promoted winners ran out of reach at ~1.7k.
3. **Subscribers can't grow without reach or recurrence.** The upload stream
   stopped mid-Aug (run failures); reach was a one-week spike, so there was no
   returning-audience loop and basically zero subscriber conversion.

## The path (retention → consistency → eventual virality)

1. **Keep driving retention %.** 14-20s runtimes so ~10s of watch time reads
   as 60-70% instead of ~40%; hook inside the first 2 seconds; escalation
   every 2-3s; re-read twist endings that trigger replays.
2. **Never miss a day, keep the cap at 2.** Consistency teaches the algorithm
   who the channel's audience is. Raising the cap back to 10 just revives the
   dump problem.
3. **Crosspost the finished Short** to Instagram Reels / TikTok / Facebook
   (nothing in this repo does that yet — it's the fastest way to pull a
   partial audience over, and the sync shortcut is: seed the titles off the
   same `output/` folder).
4. **Iterate monthly on data.** The next export (≈ late Oct) should show avg %
   viewed climbing from ~43% toward 60-70%, a growing median views/Short, and
   subscribers starting to tick between view spikes.

## What this repo changes

- **Retention window**: 14-19s (`story.min_seconds: 14`, `max_seconds: 20`)
  with a code-enforced 32-44 word gate so the model can't blow past it;
  prompt enforces hook-by-second-2, replay-loop endings.
- **Engagement**: the saga closing line opens with a comment question at the
  highest-attention moment ("What would you do? Part 2 drops tomorrow — follow
  TinyPop TV so you don't miss it."), so the finale of every part drives a
  like/comment reaction, not just a subscribe CTA (2026 analytics: 0.9% like
  rate, 0 recurring comments).
- **Cadence**: 2/day cap (`schedule.daily_upload_target: 2`, workflow
  `--target 2`); sessions stay spaced so uploads never arrive in a batch.
- **Reliability**: OpenRouter rotation + dead-model discovery, published OAuth
  app → the daily beat finally runs every day.
- Everything else (the actual viral outcome) is decided by viewer retention —
  which is now the thing the pipeline optimizes for.

## Realistic expectation

Retention fixes compound: from ~43% to ~60-70%, most Shorts should start
clearing the first test pool (a few hundred → few thousand views) instead of
capping at ~1.7k, and subscriber conversion should move from ~0.02% toward the
industry 0.5-1.5%. A breakout hit is possible but not guaranteed — no pipeline
can *promise* a specific view count.
