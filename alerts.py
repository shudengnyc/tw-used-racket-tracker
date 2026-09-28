#!/usr/bin/env python3
"""Deal alerts: tell the owner when a new listing matches their watch list.

A quarter of used listings sell within four days, so checking the page is
not fast enough. After each scrape the workflow runs this: every listing that
appeared (or was repriced) in the last 24 hours is checked against watch.json,
and new matches become one GitHub issue that @-mentions the repo owner --
GitHub then emails them and pushes to its mobile app. No accounts or services
beyond the repo itself.

alerted.json remembers which listing-at-a-price has been reported, so a match
is sent once, whichever run -- a scheduled scrape or a push from the Mac --
sees it first. A markdown is a new price, so it alerts again.

    python3 alerts.py --dry-run    # print what would be sent; send nothing
    python3 alerts.py --test       # send one sample alert, marked TEST; record nothing

watch.json is a list of watches. Every field is optional; a listing must pass
all the fields a watch sets, and matching any one watch is enough:

    {"name": "Blade 98 in my grip",          # shown in the alert
     "q": "Blade 98",                        # racquet name contains (any case)
     "brands": ["Wilson"],
     "grades": ["Grade A", "Grade B"],
     "grips": ["4 3/8\\""],
     "max_price": 180,
     "min_discount": 30,                     # % off the new price
     "signals": ["lowest ever", "below usual", "markdown"],   # any of
     "specs": {"head_min": 97, "head_max": 100, "wt_min": 11,
               "wt_max": 11.6, "sw_min": 310, "sw_max": 330,
               "st_min": 60, "st_max": 66}}
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH_PATH = os.path.join(HERE, "watch.json")
ALERTED_PATH = os.path.join(HERE, "alerted.json")
SNAP_PATH = os.path.join(HERE, "snapshot.json")
LABEL = "deal-alert"

# specs keys in a watch (the same names the page's spec filters use) -> the
# numeric field on a listing they bound.
SPEC_FIELDS = {"head": "head_in2", "wt": "weight_oz", "sw": "swingweight",
               "st": "stiffness"}
SIGNALS = {
    "lowest ever": lambda r: r.get("verdict") == "LOWEST EVER",
    "below usual": lambda r: r.get("verdict") == "BELOW USUAL",
    "markdown": lambda r: bool(r.get("was_price")),
}


def key(r):
    """The same listing-at-a-price key seen.json uses."""
    return f"{r['sku']}|{r['used_price']}"


def matches(r, w):
    """True when listing r passes every condition watch w sets."""
    if r.get("new_cheaper"):
        return False                       # never alert on a "buy new" trap
    if w.get("q") and w["q"].lower() not in r["racquet"].lower():
        return False
    if w.get("brands") and r["brand"] not in w["brands"]:
        return False
    if w.get("grades") and r["grade"] not in w["grades"]:
        return False
    if w.get("grips") and r["grip"] not in w["grips"]:
        return False
    if w.get("max_price") is not None and r["used_price"] > w["max_price"]:
        return False
    if w.get("min_discount") is not None and (r.get("discount_pct") or 0) < w["min_discount"]:
        return False
    if w.get("signals") and not any(SIGNALS[s](r) for s in w["signals"]):
        return False
    nspec = r.get("nspec") or {}
    for short, field in SPEC_FIELDS.items():
        lo = (w.get("specs") or {}).get(f"{short}_min")
        hi = (w.get("specs") or {}).get(f"{short}_max")
        if lo is None and hi is None:
            continue
        val = nspec.get(field)
        if val is None or (lo is not None and val < lo) or (hi is not None and val > hi):
            return False
    return True


def check_watches(watches):
    """Raise ValueError naming the first mistake, so a typo fails loudly."""
    if not isinstance(watches, list):
        raise ValueError("watch.json must be a list of watches")
    allowed = {"name", "q", "brands", "grades", "grips", "max_price",
               "min_discount", "signals", "specs"}
    for i, w in enumerate(watches):
        where = f"watch {i + 1} ({w.get('name', 'unnamed')})"
        unknown = set(w) - allowed
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
        bad = set(w.get("signals", [])) - set(SIGNALS)
        if bad:
            raise ValueError(f"{where}: unknown signal(s) {sorted(bad)}; "
                             f"use {sorted(SIGNALS)}")
        spec_ok = {f"{s}_{m}" for s in SPEC_FIELDS for m in ("min", "max")}
        bad = set(w.get("specs", {})) - spec_ok
        if bad:
            raise ValueError(f"{where}: unknown spec(s) {sorted(bad)}")


def pending(listings, watches, alerted):
    """[(listing, [watch names])] new in the last day, matched, not yet sent."""
    out = []
    for r in listings:
        if not r.get("is_new") or key(r) in alerted:
            continue
        names = [w.get("name") or "Watch" for w in watches if matches(r, w)]
        if names:
            out.append((r, names))
    out.sort(key=lambda m: (-(m[0].get("discount_pct") or 0), m[0]["used_price"]))
    return out


def _tidy(name):
    return " ".join(w for w in name.split() if w.lower() not in ("racquet", "racquets"))


def _signal(r):
    if r.get("verdict") == "LOWEST EVER":
        return "lowest ever"
    if r.get("was_price"):
        return f"was ${r['was_price']:.0f}"
    if r.get("verdict") == "BELOW USUAL":
        return "below usual"
    return "new"


def title(found):
    first = found[0][0]
    more = f" + {len(found) - 1} more" if len(found) > 1 else ""
    return (f"Deal alert: {_tidy(first['racquet'])} ${first['used_price']:.0f} "
            f"({first['grade'].replace('Grade ', '')}, {first['grip'] or 'grip ?'}){more}")


def body(found, owner=None, page_url=None):
    lines = []
    if owner:
        lines.append(f"@{owner} — {len(found)} new listing"
                     f"{'s' if len(found) > 1 else ''} match your watch list.\n")
    lines += ["| Racquet | Price | Off new | Grade | Grip | Signal | Watch |",
              "|---|---|---|---|---|---|---|"]
    for r, names in found:
        off = f"{r['discount_pct']}%" if r.get("discount_pct") not in (None, "") else ""
        lines.append(f"| [{_tidy(r['racquet'])}]({r['url']}) | ${r['used_price']:.0f} "
                     f"| {off} | {r['grade'].replace('Grade ', '')} | {r['grip']} "
                     f"| {_signal(r)} | {', '.join(names)} |")
    lines.append("")
    if page_url:
        lines.append(f"All listings: {page_url}")
    lines.append("Used racquets sell fast — a quarter are gone within four days. "
                 "Edit `watch.json` to change what alerts you; close this issue "
                 "when you're done with it.")
    return "\n".join(lines)


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the alert that would be sent; send and record nothing")
    ap.add_argument("--test", action="store_true",
                    help="send one sample alert built from a current listing, "
                         "marked TEST, to check delivery; records nothing")
    args = ap.parse_args()

    watches = _load(WATCH_PATH, [])
    check_watches(watches)
    snap = _load(SNAP_PATH, None)
    if not watches or not snap:
        print("No watches or no snapshot -- nothing to check.")
        return 0
    listings = snap["listings"] if isinstance(snap, dict) else snap
    alerted = set(_load(ALERTED_PATH, []))

    if args.test:
        # The best current deal, whether or not it is new or watched -- it only
        # has to look like the real thing.
        best = max((r for r in listings if not r.get("new_cheaper")),
                   key=lambda r: r.get("discount_pct") or 0)
        found = [(best, ["TEST"])]
    else:
        found = pending(listings, watches, alerted)
    if not found:
        print(f"No new matches for {len(watches)} watch(es).")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or (repo.split("/")[0] or None)
    page = f"https://{owner}.github.io/{repo.split('/')[1]}/" if "/" in repo else None
    t, b = title(found), body(found, owner, page)
    if args.test:
        t = "TEST — " + t
        b = ("**This is a test alert** — nothing new matched; this checks that "
             "alerts reach you. Real ones look exactly like this.\n\n" + b)
    if args.dry_run:
        print(t, "\n", b, sep="")
        return 0

    # Idempotent: creates the label the first time, leaves it alone after.
    subprocess.run(["gh", "label", "create", LABEL, "--color", "c3dc22",
                    "--description", "New listing matching watch.json", "--force"],
                   check=False, capture_output=True)
    r = subprocess.run(["gh", "issue", "create", "--title", t, "--body", b,
                        "--label", LABEL], capture_output=True, text=True)
    if r.returncode:
        print(f"Couldn't open the alert issue: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Alerted: {r.stdout.strip()}")
    if args.test:
        return 0                           # a test records nothing

    # Remember what was sent. Keys for listings no longer on sale are dropped,
    # which keeps the file as small as the current catalog.
    live = {key(r) for r in listings}
    sent = (alerted | {key(r) for r, _ in found}) & live
    with open(ALERTED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, indent=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
