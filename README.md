# Used racquet tracker

Tracks used racquet prices at [Tennis Warehouse](https://www.tennis-warehouse.com)
and builds a browsable report from them.

**Published report: https://shudengnyc.github.io/tw-used-racket-tracker/**

The used catalog page only shows *new* prices; the real used prices live on each
racquet's own `orderusedproduct.html` page. So a run fetches the catalog once for
the racquet list, then one page per racquet — about 62 requests, five seconds.

Every run appends to `history.csv`, and each listing is judged against *that
racquet's own past prices* rather than one blunt threshold, so "cheap" means
cheap for that frame. See [How listings are judged](#how-listings-are-judged).

Brands tracked: Wilson, Yonex, Tecnifibre, Head, Prince, Solinco.

## Using it

```sh
./racket                  # scrape now (~8s), rebuild the report, sync to GitHub
./racket --open           # ...and open it in the browser
./racket --deals          # only new listings, markdowns and historically notable prices
./racket --trend "Blade"  # price history for one racquet
./racket --max-price 150 --grip "4 3/8"
```

Double-clicking **Check Racquets.command** in Finder does `--open`, and the
**Check Racquets** macOS Shortcut runs the same thing from Spotlight.

Filters (`--brands`, `--deals`, `--max-price`, `--grip`) narrow the printed
table only. The HTML report always covers everything, because it has its own
filter controls built in.

### Reading someone else's scrape instead of making your own

```sh
./racket --pull      # show what the scheduled GitHub run last gathered
./racket --refresh   # make GitHub scrape now, wait (~20s), then show it
```

`--refresh` is slower than just scraping here. It is worth it when you want the
*published* page updated too, since that only rebuilds when GitHub runs.

## How it fits together

Two machines scrape: this Mac, and a scheduled GitHub Actions job. They share
one price history through the repo.

```
  ./racket ──scrape──> report.html ──> commit + push ──┐
                                                       ├──> history.csv (shared)
  GitHub Actions ──scrape──> site/index.html ──────────┘         │
     6x a day                      │                             │
                                   └──> GitHub Pages <───────────┘
```

A push from the Mac also triggers the workflow, which republishes the page from
the pushed data without scraping again.

### Two writers, one history

`history.csv` is append-only and has two writers, so `.gitattributes` marks it
`merge=union`: a merge keeps every line from both sides instead of raising a
conflict. That can leave duplicate rows, so `dedupe_history()` runs after any
pull or merge and collapses identical ones.

`append_history` also skips anything already recorded for that racquet at that
price today, so a day of frequent scraping produces ~130 rows, not thousands. A
price that genuinely *moves* mid-day still gets its own row.

### Why the scrape doesn't run in the browser

The published page cannot fetch Tennis Warehouse itself — TW sends no
`Access-Control-Allow-Origin` header, so browsers block it. It also cannot start
the workflow, because that needs a token with `actions: write` and this repo is
public, so embedding one would publish a credential anyone could write with.
Hence the schedule, and a **Check for new prices** button that re-fetches the
published page rather than pretending to scrape.

That button cache-busts on purpose: Pages serves the report with
`Cache-Control: max-age=600`, so a plain reload inside ten minutes would quietly
re-show the cached copy and look broken.

## How listings are judged

The Signal column, in priority order:

| Signal | Meaning |
|---|---|
| **buy new** | The new racquet costs the same or less (a clearance). Sinks to the bottom. |
| **lowest ever** | Cheaper than any past price it is compared against. |
| **was $…** | This exact racquet (same SKU) carried a higher price before — a markdown. |
| **below usual** | At or under 90% of the typical past price. |
| **new** | This listing, at this price, first appeared in the last 24 hours. |
| above usual / typical | At or over 110% of typical / in between. |
| — | Not enough history to say. |

"Past prices" counts each listing **once per price it carried**, not once per
day it sat there. A used racquet often sits unchanged for weeks, and counting
days let that one listing outvote everything else, so nearly every row read
"typical".

A listing is compared with its own racquet and grade when that has at least 3
distinct past prices. Otherwise every grade of the same racquet is pooled in,
each price rescaled by the usual gap between grades (learned from the data each
run: A runs ~4-5% above B, C ~8% below), and that pool needs at least 4.
Hovering a signal shows which comparison it used. Thresholds live at the top of
`tw_used.py`; `tools/eval_judge.py` shows what a change would have done to past
data. The measured trade-offs, and a rejected alternative, are in
[ROADMAP.md](ROADMAP.md).

## Files

| | |
|---|---|
| `tw_used.py` | Scraping, history, judging, git sync, CLI (settings at the top) |
| `report.py` | Builds the HTML report (local build self-contained; Pages build links fonts and thumbnails) |
| `histfile.py` | The one reader for `history.csv` |
| `tests/` | Parser and judging tests against saved pages |
| `tools/eval_judge.py` | Replays history to compare judging methods |
| `DATA.md` | Field-by-field schemas of the data files |
| `ROADMAP.md` | Follow-ups, parked ideas, and why things are the way they are |
| `racket` | CLI wrapper — run it from anywhere |
| `Check Racquets.command` | Double-clickable Finder entry point |
| `snapshot.json` | Exact round-trip of the last scrape's rows; what a rebuild reads |
| `used_prices.csv` | The same rows, for opening in a spreadsheet |
| `history.csv` | Append-only price log, one row per racquet/grade/price/day |
| `seen.json` | Previous listings, for "new or repriced" detection |
| `thumbs/`, `thumbs_large/` | Cached images — 56px thumbnails, 400px for the lightbox |
| `fonts.css` | Fonts as base64, so the page renders identically offline |

`report.html` (local build) and `site/` (published build) are generated and
gitignored. They differ — the local one carries a **Local** tag and the Shortcut
refresh button — which is why they are separate files rather than one that each
side could overwrite.

Do not rebuild from `used_prices.csv`. It stringifies everything and stores
`specs`/`nspec` as Python dict reprs, so reloading it would turn `12` into
`"12"` and break the sorting and filtering the report's JavaScript does.
`snapshot.json` exists for that.

## The scheduled run

`.github/workflows/check-racquets.yml` runs six times a day, every three hours
from 6:17am to 9:17pm Pacific (off the hour, where GitHub's scheduler is less
crowded), and on push. Cron is UTC and has no notion of DST, so
from November to March those land an hour earlier.

Actions and Pages are free on public repositories. A run takes ~25s, of which
the scrape is ~5s and the rest is GitHub's own setup and Pages deploy.

Two things worth knowing:

- GitHub disables scheduled workflows after 60 days of repo inactivity. Every
  run commits, which resets that clock, so it should never trigger.
- The repo grows ~50–70 MB/year, since each run rewrites `snapshot.json` and
  `used_prices.csv`. Fine for years; if it ever matters, `used_prices.csv` is
  derivable from `snapshot.json` and could stop being tracked.

## Making changes

Run the tests before pushing — CI runs them before every scrape, and a failure
stops the run before anything is recorded:

```sh
python3 -m unittest -v
```

Common changes:

- **Add a brand.** Append it to `TARGET_BRANDS` in `tw_used.py`. If its model
  lines are two words ("Pure Drive"), add them to `TWO_WORD` in `report.py` so
  the Lines filter groups them.
- **Tune the signals.** Edit `MIN_OBS`, `MIN_OBS_POOL`, `BELOW_USUAL` or `HIGH`
  at the top of `tw_used.py`, then `python3 tools/eval_judge.py` to compare with
  the old verdict counts over all recorded days. To try a new method, add a
  function to `METHODS` in that script first.
- **Tennis Warehouse changed its page layout.** The scheduled run fails: exit 2
  (no listings parsed) or 3 (many pages failed to load), and GitHub emails you.
  Nothing is recorded, and the page keeps the last good data. Save fresh copies
  of the pages over `tests/fixtures/*.html.gz`, fix the regexes in `tw_used.py`
  until `python3 -m unittest` passes, and update the expected values in
  `tests/test_parse.py`.
- **Change the page.** It is one template string in `report.py` (HTML, CSS
  and JS). Anything from Tennis Warehouse must go through `esc()` before it
  reaches `innerHTML`. Preview with `./racket --pull --open`, which rebuilds
  from the last snapshot without scraping.
- **Change how the table sorts.** Every sort is one entry in `SORTS` in
  `report.py`: its label, which direction it starts in, and the words on the
  direction button. `DEFAULT_SORT` is what a first-time visitor sees; after
  that each browser remembers the last sort picked.
- **Add a field to listings.** Add it in `parse_listings` (or `main()` for
  derived fields), to the `payload` key list in `write_html`, and to
  [DATA.md](DATA.md). Old snapshots lack it, so read it with `.get()`.

Pushing `tw_used.py`, `report.py`, `histfile.py` or `snapshot.json` republishes
the page from the current snapshot without re-scraping. New verdict logic only
shows up after the next scrape, or run the workflow by hand:
`gh workflow run check-racquets.yml`.

## Setup elsewhere

Needs Python 3 (standard library only — no `pip install`) and, for syncing,
`git` plus the [`gh` CLI](https://cli.github.com) authenticated via
`gh auth login`. Without `gh`, everything except `--refresh` still works.

Pages is configured to build from the workflow. If it ever needs re-enabling:

```sh
gh api -X POST repos/OWNER/REPO/pages -f build_type=workflow
```

Don't set `enablement: true` on `actions/configure-pages` instead — it needs an
admin token the workflow's `GITHUB_TOKEN` doesn't have.
