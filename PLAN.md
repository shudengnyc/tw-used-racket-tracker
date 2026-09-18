# Improvement plan

Written 2026-09-18 from a review of the whole app. Items are ordered by
payoff-for-effort. Each one is self-contained: do them in any order, one
per commit, and tick the checkbox when it lands.

Baseline at review time, for comparison later:

| Measure | Value |
|---|---|
| Listings in snapshot | 90 across 45 racquets |
| Verdicts | 86 typical, 1 below usual, 1 high, 2 none |
| History | 4,286 rows, 38 days, 147 racquet+grade keys |
| Keys whose history is a single SKU | 95 of 147 |
| Scheduled runs actually landing | ~4 of 6 per day |
| `report.html` size | 483 KB (151 KB fonts, ~153 KB thumbnails) |

---

## Phase 1 — Reliability (small, do first)

### 1.1 Fail the CI run when the scrape returns nothing  `[x]`

**Problem.** `main()` prints "No listings returned" and returns `None`, so the
job exits 0, nothing commits, and the only symptom is the 12-hour staleness
banner on the page.

**Change.** In `tw_used.py`, `main()`:

```python
if not listings:
    print("No listings returned -- the page layout may have changed.", file=sys.stderr)
    return 2
```

GitHub emails on a failed workflow, so this is the alert.

Note: `main()` has other bare `return`s (`--trend`, the `--pull` path) that
mean success; only this one changes. `sys.exit(main())` already propagates it.

**Verify.** Temporarily break `ROW_RE`, run `python3 tw_used.py --no-sync --no-push`,
confirm exit code 2 (`echo $?`). Restore.

### 1.2 Do not record a partial scrape  `[x]`

**Problem.** `get_used_listings` swallows fetch errors per racquet and returns
`[]`. If 20 of 62 product pages fail, the run still appends history and
rewrites `seen.json`, so every missed SKU loses its first-seen date and comes
back as "new" next run, and the page silently under-reports.

**Change.**
- Make `get_used_listings` return `(rows, ok)` or raise a sentinel; count
  failures in `main()`.
- If failures exceed a threshold (suggest `max(2, len(catalog) // 10)`),
  print a summary, skip `append_history`, skip the `seen.json` rewrite, skip
  `snapshot.json`, and return non-zero. Still write the HTML from the last
  good snapshot so a local run shows something.
- Keep the per-racquet `!` line on stderr so the log names the failures.
- Count *fetch exceptions*, not empty results: a racquet with no used stock
  legitimately returns `[]`.
- The check must sit before `append_history` (currently right after the
  `fetch_thumbs` call). Thumbnails fetched before the abort are harmless.
- In CI a non-zero exit skips the commit and deploy steps, so the published
  page stays on the last good data. That is intended; 1.1 and 1.2 share the
  same failure email.

**Verify.** Point `BASE` at an invalid host for a test run and confirm the
history file is untouched (`git diff --stat history.csv` is empty).

### 1.3 Move the cron off the top of the hour  `[x]`

**Problem.** `gh run list` shows 3-4 scheduled runs per day against 6 slots.
GitHub delays or drops `:00` crons under load.

**Change.** `.github/workflows/check-racquets.yml`:

```yaml
- cron: "17 13,16,19,22,1,4 * * *"
```

Update the comment block above it and the README sentence about times.

**Verify.** After a week:
```sh
gh run list --workflow check-racquets.yml --limit 60 --json createdAt,event \
  --jq '[.[]|select(.event=="schedule")|.createdAt[0:10]]|group_by(.)|map("\(.[0]) \(length)")|.[]'
```
Expect 6 per day.

### 1.4 Let the CI commit step self-heal on a race  `[x]`

**Problem.** If the Mac pushes during the ~25 s CI scrape, the workflow's
`git pull --rebase` conflicts on `snapshot.json` / `used_prices.csv` /
`seen.json` (only `history.csv` is `merge=union`) and the job fails.

**Change.** In the "Commit price history" step:

```sh
if ! git pull --rebase; then
  git checkout --theirs -- used_prices.csv seen.json snapshot.json  # CI's data is newer
  git add used_prices.csv seen.json snapshot.json
  GIT_EDITOR=true git rebase --continue || { git rebase --abort; exit 1; }
fi
python3 -c "import tw_used; tw_used.dedupe_history()" && \
  { git diff --quiet history.csv || git commit -qam "De-duplicate history after merge"; }
git push
```

`--autostash` is dropped: everything is committed by this point. The dedupe
mirrors `push_to_github`, since a `merge=union` rebase can leave duplicate
rows.

Note the side: during a rebase, `--theirs` is the commit being replayed
(ours from CI), which is the fresher scrape.

**Existing bug, same fix.** `push_to_github` in `tw_used.py` resolves the
same conflict with `git checkout --ours`, which during a rebase is the
*upstream* side, i.e. it keeps GitHub's older snapshot and throws away the
Mac's fresh one. Change it to `--theirs` in the same commit.

**Verify.** Hard to reproduce on demand; rely on reading the step log the
next time a run and a Mac push overlap.

---

## Phase 2 — Signal quality (the substantive change)

### 2.1 Decide what "history" means for `judge()`  `[ ]`

**Problem.** A racquet+grade's history is mostly one SKU sitting at one price
for weeks. The median converges on the current price, so almost everything
reads "typical". The `was $` markdown signal papers over this for SKUs that
moved, but the racquet-level verdicts carry no information.

Measured on 2026-09-12 data:

| History definition | typical | below | high | none (< MIN_OBS) |
|---|---|---|---|---|
| Every row (current) | 86 | 1 | 1 | 2 |
| Distinct (sku, price) pairs | 28 | 1 | 0 | 61 |

The honest version fires far less, because there is not yet much independent
data. Choose one of these approaches, or layer them:

**Option A — distinct observations (minimal change).**
Build `hist` from `{(sku, price)}` per key instead of rows. Signals become
truthful; most rows show "—" until more distinct listings have passed through.
Best if you value precision over coverage.

**Option B — widen the pool.**
Judge against the racquet across *all* grades, applying a grade offset learned
from the data (median A-to-B and B-to-C gap across all racquets). Roughly
triples the sample per key. Add a `pool` field to the verdict tooltip so the
page says what it compared against.

**Option C — judge the discount, not the price.**
Tennis Warehouse's new price anchors the used one. Compute each listing's
`discount_pct` and compare it with the typical discount for that racquet
(or brand+grade when the racquet is thin). Robust to new-price changes and
to model-year turnover. Likely the strongest signal long term.

**Recommended path.** Ship A now (one afternoon), collect another month, then
evaluate B and C against the accumulated data using the same kind of
counter table as above. Keep `MIN_OBS = 3` for A; consider 5 for B/C.

**Where.** `tw_used.py`: `load_history`, `judge`. `report.py`: the Signal
column tooltip and the `notes` paragraph that explains signals.

**Verify.** Write a one-off script (keep it in `tools/eval_judge.py`) that
replays history day by day and prints the verdict distribution per method.
That is also how you compare B and C later.

### 2.2 Fix model-line grouping  `[ ]`

**Problem.** `familyOf()` in `report.py` takes the word after the brand, so
"Wilson Pro Staff" and "Wilson Pro Labs" both become "Pro", and "Babolat Pure
Drive" / "Pure Aero" would merge if Babolat is ever added.

**Change.** Add a small alias table of two-word lines and match it first:

```js
const TWO_WORD = ['Pro Staff','Pro Labs','Pure Drive','Pure Aero','Pure Strike',
                  'Speed Pro','Graphene 360'];
```

Fall back to the single word otherwise. Drop `Graphene 360` from the list:
it is a Head technology prefix, and for names like "Head Graphene 360+ Speed"
the line is the word after it. Handle it (and similar prefixes) with a
small skip-list instead.

**Verify.** Filter the page to Wilson and check the Lines row shows
"Pro Staff" and "Ultra", not "Pro".

---

## Phase 3 — Page weight and robustness

### 3.1 Slim the published build  `[ ]`

**Problem.** 483 KB per load, and every 10-minute rebuild invalidates all of
it because fonts and thumbnails are inlined into the HTML.

**Change.** Only for `--html-mode pages`:
- Write `site/fonts.css` and link it with `<link rel="stylesheet">` instead
  of inlining `FONT_CSS`.
- Copy `thumbs/` into `site/thumbs/` in the workflow (next to the existing
  `thumbs_large` copy) and emit `thumbs/{code}.jpg` paths in `THUMBS`
  instead of data URIs.
- Keep the `local` build fully inlined so it stays a single offline file.
- Fix the lightbox fallback at the same time: it compares `this.src`
  (always absolute) with `THUMBS[code]`. With relative paths these never
  match, so a missing thumb as well as a missing large image would loop on
  `error` forever. Compare `this.getAttribute('src')`, or set a
  `data-fell-back` flag.
- Copy the repo's `fonts.css` into `site/` in the same step; `site/` is
  gitignored and rebuilt each run.

Expected result: HTML drops to ~180 KB; fonts and images are cached by the
browser across rebuilds.

**Where.** `report.py` `write_html` (branch on `mode`), `load_thumbs`,
workflow "Assemble the Pages site" step.

**Verify.** `ls -l site/index.html` before and after; open the published
page with DevTools Network tab and confirm fonts return 304 on reload.

### 3.2 Escape data going into the DOM  `[ ]`

**Problem.** Racquet names, brands and spec strings are inserted with
innerHTML and into `data-brand="…"` attributes unescaped. The JSON payload
only escapes `<` to protect the `<script>` block. No current name contains
`& " <`, but the strings come from Tennis Warehouse.

**Change.** Add to the template script:

```js
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
```

Apply in `thumb`, `details`, `buildBrands`, `buildFamilies`, the row
template (`tidy(r.racquet)`, `r.brand`, `r.grade`, `r.grip`), `openLb`, and
`stateLabel`. Replace the ad-hoc `.replace(/"/g,'&quot;')` calls.

**Verify.** Temporarily rename one listing in `snapshot.json` to
`Test "Quote" & <b>bold</b>` and run `--pull`; the name must render
literally and the brand pill must still filter.

### 3.3 Hoist `SPEC_IDS`  `[ ]`

`SPEC_IDS` is a `const` declared near the bottom of the script but used by
functions defined above it. It works only because nothing calls them before
that line. Move the declaration up next to `RANK`.

### 3.4 Fix nested buttons in saved-search pills  `[ ]`

`.spill` is `role="button"` and contains a `role="button"` remove icon.
Make the pill a plain `span`, give the label its own `<button>`, keep the
✕ as a second `<button>`. Update the click handler to use `closest('button')`.

---

## Phase 4 — Maintainability

### 4.1 Fixture tests for the scraper  `[ ]`

**Problem.** The scraper is five regexes with no test. A layout change is
only caught in production (and, until 1.1 lands, silently).

**Change.**
- Save one catalog page and one product page under `tests/fixtures/`
  (`fetch()` them once, ~500 KB gzip-compressed each is fine).
- `tests/test_parse.py` with plain `unittest` (no pip):
  - `get_catalog`-style parsing on the fixture yields N racquets with a
    known first code, name, brand, new price.
  - Product-page parsing yields the expected rows: grade, grip, price, stock.
  - `parse_specs` / `numeric_specs` round-trip the known spec table.
  - `judge` and `marked_down_from` on hand-built histories.
- Refactor `get_catalog` and `get_used_listings` so the parsing is a pure
  function of `page` text that the fetch wrappers call.
- Add a `test` job to the workflow that runs `python3 -m unittest` before
  `check`, or a separate `on: pull_request` workflow.

**Verify.** `python3 -m unittest -v` passes locally and in CI.

### 4.2 Read `history.csv` once per run  `[ ]`

`load_history`, `load_sku_prices`, `_history_dates`, `dedupe_history` and
`load_series` each re-read the file. Add `load_history_rows()` returning the
list of dicts and pass it down (or memoise). Trivial at 370 KB today; mainly
a simplification so the five functions share one parser and one error path.

### 4.3 Tidy imports  `[ ]`

`from report import write_html` sits at line 446 of `tw_used.py`. Move it to
the import block at the top.

### 4.4 Document the data contract  `[ ]`

Add a short `DATA.md` (or a README section) listing each field in
`snapshot.json` listings with type and meaning, and the `seen.json` and
`history.csv` schemas. Both `report.py` and any future eval script depend on
them, and the README currently only says "do not rebuild from
`used_prices.csv`".

---

## Ideas parked for later

Not planned; recorded so they are not re-derived.

- **Watchlist alerts.** A saved search already exists client-side. A
  server-side version (a `watch.json` of filters in the repo, checked in
  CI, emailing via a GitHub Issue or `gh api` notification) would turn the
  tracker from pull to push.
- **Sold-through tracking.** A SKU disappearing from the catalog means it
  sold or was pulled. Recording the disappearance date and final price would
  tell you how long deals actually last and what price clears.
- **More brands.** Babolat and Dunlop are the obvious gaps. Adding them is a
  one-line change to `TARGET_BRANDS` but doubles page count and will surface
  the `familyOf` issue in 2.2 immediately.
- **Retire `used_prices.csv` from git.** README already notes it is derivable
  from `snapshot.json`. Do it if repo growth ever matters.

---

## Suggested order

1. Phase 1 in one sitting (1.1, 1.3 are five-minute changes; 1.2 and 1.4 an hour).
2. 2.1 Option A plus the eval script, then wait for data.
3. 4.1 tests, since every later change to the scraper benefits.
4. Phase 3 as a single "page" commit.
5. 2.1 B/C evaluation once a month or two of history has accumulated.
