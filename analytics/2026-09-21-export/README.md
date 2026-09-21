# Analytics export — 2025-09-21 → 2026-09-21 (exported 2026-09-21)

Source: channel analytics export (the raw `Content *.zip` is gitignored; these
three CSVs are the extracted, normalised data). Compare against
`analytics/2026-08-08-baseline/` to measure the effect of the retention /
cadence changes made in Sep 2026.

## Channel totals (full year)

| Metric | Value |
|---|---|
| Videos published | 85 (6 gameplay 2024, 79 story Shorts Aug 2026) |
| Views | 10,543 |
| Engaged views | 2,969 |
| Watch time | 13.4 hrs |
| Unique reach | 7,993 |
| Avg % viewed (winners) | ~40-45% |
| Subscribers gained / lost | +5 / 0 (channel: 3 total) |
| Likes / Comments / Shares | 95 / 0 / 0 |
| Videos > 1,000 views | 3 (max 1,795) |

## Deep-dive (re-analysis, 2026-09-21)

Same export re-mined for the subscriber/engagement goal. The flood theory
holds, plus three things the first pass under-weighted:

1. **Engagement is ~zero and that's a promotion blocker.** Only 95 likes all
   year on 10,543 views = **0.9% like rate** (healthy Shorts run 3-5%). Zero
   recurring comments, 2 shares, engaged viewers converted to **0 subscribers**
   (channel total: 3). YouTube's Shorts loop weighs likes/comments/shares on
   top of retention; at 0.9% the algorithm gets no positive feedback to
   expand a test pool even when retention is decent.
2. **In the original saga mode, the narration ending had NO engagement hook** —
   the saga block ("Part 2 drops tomorrow — follow…") overrode the generic
   prompt's "end with a question to invite comments" rule. So the single
   highest-retention moment (the last line) was pure CTA with zero comment
   bait. Fixed Sep 2026: the closing line now opens with a comment question —
   "What would you do? Part 2 drops tomorrow — follow TinyPop TV so you don't
   miss it." (finale: "What would you have done?…").
3. **Duration vs retention (confounded, but confirms the direction).** 20-27s
   videos averaged 436 views vs 45 for 35s+ — but day-of-flood confounds all
   of it (Aug 7→5234, Aug 9→2284, Aug 15→0 as each day deeper in the flood
   got less of a test pool). What it does confirm: nothing after the first
   launch day ever got distributed, so every retention/duration signal from
   Aug 2026 is polluted. The 14-20s policy stands on the retention math, and
   we tightened the hard cap 48→44 words so a 12s real watch time clears the
   ~65% promotion bar instead of landing at ~60%.

## What we changed (Sep 2026, see git log / IMPLEMENTATION.md)

- **Cadence: 10/day → 2/day.** `schedule.daily_upload_target: 2` + workflow
  `--target 2`. Two spread-out Shorts/day keep every upload in rotation
  instead of starving a batch. (Don't raise this back — the Aug dump was the
  single biggest killer.)
- **Retention window: 20-30s → 14-20s, hard cap 44 words.** `story.min_seconds:
  14`, `story.max_seconds: 20`, `min_words/max_words: 32/44`. The same ~10-11s
  of watch time now lands at ~60-70% retention instead of ~40%, which is the
  range YouTube promotes. The Aug 47.5s-narration failure proved the word cap
  must be enforced in code.
- **Engagement hooks where they're visible, not just in the description.** The
  saga closing line now begins with a comment question (the last 2s is the
  highest-attention moment — it should ask the viewer to react, not just to
  follow), the finale ends "What would you have done?…", and the metadata
  description keeps its open question + one subscribe line.
- **Story prompt re-written.** Front-loaded hook (first sentence carries the
  strangest image), a new escalation every 2-3s, 32-44 word target now enforced
  in code (the 21 Sep run showed the model ignores a bare prompt limit — it
  emitted a 47.5s narration; `story_generator` now discards out-of-window
  candidates), "re-read" twist endings engineered to trigger replays.
- **Publishing reliability fixed** (OpenRouter multi-key rotation + dead-model
  discovery, OAuth app published so refresh tokens stop expiring, preflight
  youtube-token check so stale tokens abort in ~2s before any generation) so
  the daily schedule actually runs every day again.

## How we measure success next export (~end of Oct 2026)

- Avg % viewed on new Shorts should climb from ~43% toward 60-70%.
- **Like rate should climb from 0.9% toward 3%+** (the comment hook + retargeted
  retention are the levers).
- Comments per Short > 0 and shares > 0 on Shorts that clear 200 views.
- Views per new Short should exceed the old ~30 median; look for a second
  Short crossing 1k views after a couple of weeks of consistent 1-2/day.
- Subscribers: any + growth (conversion happens after reach, not before).

## High-yield content playbook (engineered into the prompts, 2026-09-21)

Virality in this niche is formulaic — the algorithm promotes on retention %
first, then loops/comments/shares, then reach expands. The channel's real
failing in Aug 2026 was engagement: 0 recurring comments, 0.9% like rate, 0
subscriber conversions on ~8k reachable viewers. Content now engineers
against that:

1. **First sentence = the whole hook.** It carries the strangest image AND
   one concrete specific (exact time, name, count, material). Vague fear
   swipe-aways in the first test; a specific that reads true ("The key only
   worked when I was alone.") holds.
2. **Specificity = belief = comments.** 2-3 sensory details (exact times,
   counts, smells, one line of dialogue) make the story sound real, which
   generates "that happened to me too" / "fake" arguments — both are free
   engagement, and engagement is the feedback that promotes a Short.
3. **Loop-back endings.** The final beat echoes the first sentence (same
   object/word) so the ending folds into the opening — a viewer who re-watches
   to check re-loops the Short (a direct promotion signal).
4. **Saga parts hook strangers.** Parts 2-3 open with a self-contained
   unsettling image that needs no backstory before continuing the plot — a
   continuation that assumes you saw Part 1 bleeds retention on every new
   viewer YouTube tests the Short against.
5. **Comment question at the last moment.** The closing line of every part is
   "What would you do?" + the follow hook (finale: "What would you have
   done?"). The final 2s is the highest-attention moment; it asks for a
   reaction instead of just a follow.

Two asset-level upgrades remain (deliberate choices, not code):
- **A background-music/ambient bed** (`assets/music/` is empty) — eerie low
  volume audio is standard in high performers in this niche and lifts
  retention; the code already supports it (`video/music_selector.py`).
- **Auto-first-comment per upload** ("What would you do?" pinned-style comment;
  needs the `youtube.force-ssl` OAuth scope, not in the current token yet).