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

## Root-cause findings (why views cap ~2k, subs flat)

1. **Everything was dumped.** All 79 story Shorts went up 2026-08-07 →
   ~2026-08-16 at ~10/day. Only the 3 from the very first launch day got a
   real algorithmic test pool (1.4-1.8k views each); every video published
   after that got 1-300 views. The algorithm saw a flood, gave each Short a
   tiny slice of reach, and none could surface. Volume-batching backfired.
2. **Retention ~40% is the hard ceiling.** Winners averaged ~40-45% viewed
   (~10-11s of a 25-28s Short). YouTube scales Shorts primarily on avg %
   viewed and swipe-away rate; the threshold for leaving the first test pool
   is roughly 65%+. At ~43%, even the promoted Shorts stalled at ~1.5-1.8k.
3. **No consistency, no recurrence.** The upload stream stopped mid-Aug 2026
   (run failures + key issues). Reach was a spike, not a habit — so no
   returning-audience signal and effectively zero subscriber conversion.
4. **Impressions are a side-effect, not a lever.** Total thumbnail impressions
   for the year ≈ 1,635 (< views!) — YouTube barely showed any Short, which is
   the retention/cadence problem above, not a thumbnail problem.

## What we changed (Sep 2026, see git log / IMPLEMENTATION.md)

- **Cadence: 10/day → 2/day.** `schedule.daily_upload_target: 2` + workflow
  `--target 2`. Two spread-out Shorts/day keep every upload in rotation
  instead of starving a batch. (Don't raise this back — the Aug dump was the
  single biggest killer.)
- **Retention window: 20-30s → 14-20s.** `story.min_seconds: 14`,
  `story.max_seconds: 20`. The same ~10-11s of watch time now lands at
  ~60-70% retention instead of ~40%, which is the range YouTube promotes.
- **Story prompt re-written.** Front-loaded hook (first sentence carries the
  strangest image), a new escalation every 2-3s, 32-48 word target now enforced
  in code (the 21 Sep run showed the model ignores a bare prompt limit — it
  emitted a 47.5s narration; `story_generator` now discards out-of-window
  candidates), "re-read" twist endings engineered to trigger replays.
- **Publishing reliability fixed** (OpenRouter multi-key rotation + dead-model
  discovery, OAuth app published so refresh tokens stop expiring) so the daily
  schedule actually runs every day again.

## How we measure success next export (~end of Oct 2026)

- Avg % viewed on new Shorts should climb from ~43% toward 60-70%.
- Views per new Short should exceed the old ~30 median; look for a second
  Short crossing 1k views after a couple of weeks of consistent 1-2/day.
- Subscribers: any + growth (conversion happens after reach, not before).