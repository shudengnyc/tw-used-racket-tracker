"""Replay history day by day and count the verdicts each judging method gives.

For every recorded day, judge that day's listings against only the history
from before it -- exactly what a live run on that day would have seen -- and
tally the verdicts. Run from the repo root:

    python3 tools/eval_judge.py [--since YYYY-MM-DD]

Add a method to METHODS to compare a new approach (Option B/C in PLAN.md).
"""
import argparse
import collections
import csv
import os
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


METHODS = {
    "every row": lambda day: tw_used.load_history(before=day, distinct=False),
    "distinct (sku, price)": lambda day: tw_used.load_history(before=day),
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
            hist = build(d)
            c = collections.Counter(tw_used.judge(r, hist)[0] for r in days[d])
            total += c
            if args.daily:
                print(f"  {d}" + "".join(f"{c[v]:>13}" for v in VERDICTS))
        print(f"{name:<{width}}" + "".join(f"{total[v]:>13}" for v in VERDICTS))
        # The last day on its own is what the live page shows now.
        last = collections.Counter(tw_used.judge(r, build(dates[-1]))[0]
                                   for r in days[dates[-1]])
        print(f"{'  latest day':<{width}}" + "".join(f"{last[v]:>13}" for v in VERDICTS))


if __name__ == "__main__":
    main()
