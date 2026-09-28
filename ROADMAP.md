# Roadmap

What is still open, what was decided and why. The review of 2026-09-18 is
done; its individual changes are in git history (`git log --since=2026-09-18`).

## Follow-ups

- [x] **2026-09-28: schedule checked -- the :17 move did not help.** Still 3-4
  scheduled runs a day, starting 1-2 h late; the 6am and noon slots almost
  never ran. Replaced with an hourly trigger gated on data age (see README).
- [ ] **~2026-10-05: check scrapes now land ~6 a day.** Count commits, not
  runs (most hourly runs exit without scraping):
  ```sh
  git log --since=2026-09-29 --author=github-actions --format=%ad --date=short | sort | uniq -c
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

### Deal alerts (2026-09-28)

- Delivered as a GitHub issue that @-mentions the owner: email plus the
  GitHub app's push, with nothing else to sign up for or hold a token for.
- Only CI sends. A scrape from the Mac reaches CI as a push, and that run
  sends; `alerted.json` makes "first run to see it" the sender either way.
- Starting watches are deliberately rare ("lowest ever", 40%+ off). Any
  markdown would have alerted on 6 of 53 days; any new listing on 30. (First
  measured as 19 -- inflated by the SKU-reuse bug below.)
- Next step if wanted: a "Watch this" button on the page's saved searches
  that produces the `watch.json` entry (the fields already line up).

### Days listed and Sold (2026-09-28)

- "Sold" means gone from the site. TW doesn't distinguish sold from
  withdrawn; the notes paragraph says so rather than pretending.
- Computed at page-build time from history.csv, not stored per listing, so
  `--pull` rebuilds and old snapshots get it for free.
- Known gap: a scrape run with `--brands` narrower than TARGET_BRANDS would
  make the other brands' listings look sold on that build (and rewrites
  seen.json the same way). The scheduled run never does this.

### SKU codes are recycled (found 2026-09-28)

Tennis Warehouse gives a sold racquet's SKU code to a later, different
racquet: 57 of the first 214 codes were reused. Everything that treated a SKU
as permanent was wrong for those: 11 of 15 live "was $" markdowns were a
previous racquet's price, reused codes inherited old first-seen dates, and
the Sold tab lost 81 of its 168 listings. A listing is now identified by
`(sku, racquet)` -- `listing_id()` in tw_used.py. With that fixed, the
sell-through picture is sharper: median 6 days listed, 44% gone within 4.

seen.json and alerted.json still key on `sku|price`; a clash there needs the
same code and the same price on two racquets live at once, which can't
happen because a code is only reused after its racquet sells.

## Parked ideas

Not planned; recorded so they are not re-derived.

- **Offline support (service worker).** The published page installs to a home
  screen but is not offline-capable. A service worker could serve the last
  page instantly and refresh behind it, but stale prices shown as current are
  worse than a clear offline page, so it needs a visible "showing saved copy
  from …" state. Android Chrome also wants a service worker before it offers
  its own install prompt; iOS does not.
- **Retire `used_prices.csv` from git.** Derivable from `snapshot.json`.
- **Split `tw_used.py`** (~930 lines) into fetch/parse, history/judging and
  sync modules if it keeps growing. Its sections are already in that order.
