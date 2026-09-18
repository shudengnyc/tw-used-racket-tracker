# Data files

What each tracked data file holds. `report.py`, `tools/eval_judge.py` and the
tests all depend on these shapes, so change them here first.

## `history.csv`

Append-only price log, one row per listing per price per day. Two writers (the
Mac and the scheduled run) share it through `merge=union` in `.gitattributes`;
`dedupe_history()` collapses the repeated rows a union merge can leave. Read it
through `histfile.rows()`.

| Column | Type | Meaning |
|---|---|---|
| `date` | `YYYY-MM-DD` | Local date of the scrape |
| `brand` | str | e.g. `Wilson` |
| `racquet` | str | Full catalog name, e.g. `Wilson RF 01 Pro Racquet`. With `grade`, the key for judging and sparklines |
| `grade` | str | `Grade A` / `Grade B` / `Grade C` (condition, A best) |
| `grip` | str | e.g. `4 3/8"`; empty if not parsed |
| `used_price` | float | This listing's price that day |
| `new_price` | float | Tennis Warehouse's new price that day; empty if none |
| `sku` | str | The individual used racquet, e.g. `UR0C27A`. Stable while it is listed |

A listing that sits at one price for 30 days is 30 rows. Judging counts it once
per distinct `(sku, used_price)` — see `load_history`.

## `snapshot.json`

The last scrape, exactly as the report needs it. A `--pull` or push-triggered
rebuild reads this and does **not** re-judge, so `verdict`/`median`/`basis`
are as of the scrape.

```json
{"scraped": "2026-09-18T09:45:41.946467-07:00", "listings": [ ... ]}
```

`scraped` is zone-aware ISO 8601. Older snapshots may be a bare list of
listings or lack newer fields; readers use `.get()`.

Each listing:

| Field | Type | Meaning |
|---|---|---|
| `brand`, `racquet`, `grade`, `grip`, `sku` | str | As in `history.csv` |
| `code` | str | Tennis Warehouse product code for the model, e.g. `WRFPR`; names the thumbnail files |
| `used_price` | float | |
| `new_price` | float \| null | New price today |
| `list_price` | float \| null | Manufacturer list (MSRP), when shown crossed out |
| `discount_pct` | int \| `""` | Percent off `new_price`, rounded; `""` without a new price |
| `new_cheaper` | bool | New costs the same or less — the "buy new" trap |
| `in_stock` | int \| `""` | Units of this SKU available |
| `rating`, `reviews` | float, int \| null | Owner review score out of 5 and count |
| `specs` | object | Spec strings keyed `head`, `weight`, `balance`, `swingweight`, `stiffness`, `beam`, `composition`, `power`, `stroke`, `swing`, `griptype`, `tension`, `length`; any may be missing |
| `nspec` | object | Numbers pulled from `specs`: `head_in2`, `weight_oz`, `weight_g`, `swingweight`, `stiffness`, `balance_pts` (negative = head-light) |
| `url` | str | The live used-product page |
| `is_new` | bool | This `sku`+price first seen in the last 24 h |
| `verdict` | str | `LOWEST EVER`, `BELOW USUAL`, `typical`, `high`, or `""` (not enough history) |
| `median` | float \| null | Typical past price the verdict compared against |
| `basis` | str | What it compared against, e.g. `4 past prices across grades, adjusted to Grade C`; `""` with no verdict |
| `was_price` | float \| null | A higher price this same `sku` carried earlier (a markdown) |

## `used_prices.csv`

The same listings as `snapshot.json`, flattened for a spreadsheet. `specs` and
`nspec` are Python dict reprs and every value is a string. Nothing reads it
back; do not rebuild from it.

## `seen.json`

When each listing-at-a-price was first seen, for "new or repriced":

```json
{"UR0B21D|199.0": "2026-09-15T16:46:47"}
```

Key is `sku|used_price`; value is a local naive ISO timestamp. Rewritten each
scrape with only the current listings, so a SKU that returns at a new price
starts a new clock. A partial scrape (see `main()`) does not rewrite it.
