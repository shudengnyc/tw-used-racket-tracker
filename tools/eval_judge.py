"""Replay history day by day and count the verdicts each judging method gives.

For every recorded day, judge that day's listings against only the history
from before it -- exactly what a live run on that day would have seen -- and
tally the verdicts. Run from the repo root:

    python3 tools/eval_judge.py [--since YYYY-MM-DD]

Add a function to METHODS to compare a new approach; results so far are in
ROADMAP.md.
"""
import argparse
import collections
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tw_used  # noqa: E402

VERDICTS = ["LOWEST EVER", "BELOW USUAL", "typical", "high", ""]
LABEL = {"": "none"}


def rows_by_day(path):
    days = collections.defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["used_price"] = float(row["used_price"])
            except ValueError:
                continue
            days[row["date"]].append(row)
    return days


def own_grade_only(day):
    """Option A alone: distinct (sku, price), this racquet+grade only."""
    hist = tw_used.load_history(before=day)
    return lambda r: tw_used.rate_price(r["used_price"], hist[(r["racquet"], r["grade"])])[0] \
        if len(hist.get((r["racquet"], r["grade"]), [])) >= tw_used.MIN_OBS else ""


def every_row(day):
    """The original: every daily row counts."""
    hist = tw_used.load_history(before=day, distinct=False)
    return lambda r: tw_used.rate_price(r["used_price"], hist[(r["racquet"], r["grade"])])[0] \
        if len(hist.get((r["racquet"], r["grade"]), [])) >= tw_used.MIN_OBS else ""


def pooled(day):
    """Option B, what tw_used.judge does: own grade, else all grades rescaled."""
    hist = tw_used.load_history(before=day)
    factors = tw_used.grade_factors(hist)
    return lambda r: tw_used.judge(r, hist, factors)[0]


def discount(day, _cache={}):
    """Option C (trial): the listing's % off new vs. that racquet's usual % off.

    Falls back to brand+grade when the racquet has fewer than MIN_OBS_POOL
    distinct listings. Points, not ratios: 10 points more off than usual is
    "below usual", 10 fewer is "high".
    """
    if "rows" not in _cache:
        with open(tw_used.HIST_PATH, newline="", encoding="utf-8") as f:
            _cache["rows"] = list(csv.DictReader(f))
    seen, by_rq, by_bg = set(), {}, {}
    for h in _cache["rows"]:
        if h["date"] >= day:
            continue
        try:
            used, new = float(h["used_price"]), float(h["new_price"])
        except ValueError:
            continue
        if not new or (h["sku"], used) in seen:
            continue
        seen.add((h["sku"], used))
        off = 100 * (new - used) / new
        by_rq.setdefault(h["racquet"], []).append(off)
        by_bg.setdefault((h["brand"], h["grade"]), []).append(off)

    def verdict(r):
        try:
            new = float(r["new_price"])
        except ValueError:
            return ""
        if not new:
            return ""
        off = 100 * (new - r["used_price"]) / new
        past = by_rq.get(r["racquet"], [])
        if len(past) < tw_used.MIN_OBS_POOL:
            past = by_bg.get((r["brand"], r["grade"]), [])
        if len(past) < tw_used.MIN_OBS_POOL:
            return ""
        mid = statistics.median(past)
        if off > max(past):
            return "LOWEST EVER"
        if off >= mid + 10:
            return "BELOW USUAL"
        if off <= mid - 10:
            return "high"
        return "typical"
    return verdict


METHODS = {
    "every row": every_row,
    "A: own grade": own_grade_only,
    "B: + pooled grades": pooled,
    "C: discount (trial)": discount,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", help="only tally days on or after this date")
    ap.add_argument("--daily", action="store_true", help="print each day too")
    args = ap.parse_args()

    days = rows_by_day(tw_used.HIST_PATH)
    dates = sorted(d for d in days if not args.since or d >= args.since)
    width = max(map(len, METHODS))
    head = "".join(f"{LABEL.get(v, v):>13}" for v in VERDICTS)
    print(f"{len(dates)} days, {sum(len(days[d]) for d in dates)} listing-days\n")
    print(f"{'method':<{width}}{head}")
    for name, build in METHODS.items():
        total = collections.Counter()
        for d in dates:
            rate = build(d)
            c = collections.Counter(rate(r) for r in days[d])
            total += c
            if args.daily:
                print(f"  {d}" + "".join(f"{c[v]:>13}" for v in VERDICTS))
        print(f"{name:<{width}}" + "".join(f"{total[v]:>13}" for v in VERDICTS))
        # The last day on its own is what the live page shows now.
        rate = build(dates[-1])
        last = collections.Counter(rate(r) for r in days[dates[-1]])
        print(f"{'  latest day':<{width}}" + "".join(f"{last[v]:>13}" for v in VERDICTS))


if __name__ == "__main__":
    main()
