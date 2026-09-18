# Roadmap

What is still open, what was decided and why. The review of 2026-09-18 is
done; its individual changes are in git history (`git log --since=2026-09-18`).

## Follow-ups

- [ ] **~2026-09-25: check the schedule lands 6 runs a day.** The cron moved
  from `:00` to `:17` because only ~4 of 6 top-of-hour runs were landing.
  ```sh
  gh run list --workflow check-racquets.yml --limit 60 --json createdAt,event \
    --jq '[.[]|select(.event=="schedule")|.createdAt[0:10]]|group_by(.)|map("\(.[0]) \(length)")|.[]'
  ```
- [ ] **~2026-10-18: re-run `python3 tools/eval_judge.py`.** Watch whether the
  latest-day "none" count keeps falling for A and B, and whether C's "high"
  count drops once Tennis Warehouse's new-price sale ends (see below).
- [ ] **Confirm on the live page** that `fonts.css` returns 304 on reload
  (DevTools, Network tab). Not checked yet.

## Decisions and their evidence

### How price history is counted (judging)

Measured with `tools/eval_judge.py` on 44 days of history, latest day of 95
listings:

| Method | typical | below | high | none |
|---|---|---|---|---|
| Every daily row (old) | 93 | 0 | 1 | 1 |
| A: distinct (sku, price), own grade | 32 | 0 | 0 | 63 |
| **A + B: pool grades when own < 3 (shipped)** | 54 | 0 | 1 | 40 |
| C: % off new vs usual % off (trial) | 50 | 1 | 44 | 0 |

- Counting every row made one long-sitting listing dominate its own median,
  so almost everything read "typical" — it looked informative and wasn't.
- `MIN_OBS_POOL = 4`, not 5: at 5 the pool only reached 36 listings.
- **C was rejected for now.** Tennis Warehouse cut the new price ~$50 on 14
  racquets; every used listing of those then looks worse against new and reads
  "high" — half the page. The Off % column and "buy new" already show that.

### Page build

- The Pages build links `fonts.css` and `thumbs/` instead of inlining them
  (~495 KB to ~195 KB, and cached across rebuilds). The local `report.html`
  stays a single self-contained file so it works offline.
- No "scrape now" button on the published page: it would need a write token in
  a public repo. See the README.

### Sync

- On a push race, the newer scrape wins for the derived files; `history.csv`
  union-merges. During a rebase `--theirs` is the commit being replayed (the
  local one) — the old code had this backwards and dropped fresh scrapes.
- A scrape with more than max(2, 10%) failed pages records nothing, so missed
  listings don't lose their first-seen dates.

## Parked ideas

Not planned; recorded so they are not re-derived.

- **Watchlist alerts.** Saved searches exist client-side. A `watch.json` of
  filters checked in CI, notifying via a GitHub Issue, would turn the tracker
  from pull to push.
- **Sold-through tracking.** A SKU disappearing means it sold or was pulled.
  Recording when and at what price would show how long deals last and what
  price clears.
- **More brands.** Babolat and Dunlop are the gaps. One line in
  `TARGET_BRANDS`; `TWO_WORD` in `report.py` already has the Babolat lines.
- **Retire `used_prices.csv` from git.** Derivable from `snapshot.json`.
- **Split `tw_used.py`** (~930 lines) into fetch/parse, history/judging and
  sync modules if it keeps growing. Its sections are already in that order.
