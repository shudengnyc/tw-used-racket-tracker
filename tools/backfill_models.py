"""One-off: rebuild models.json from every snapshot.json in git history.

models.json started on 2026-09-28; racquets that sold before then are only
in old snapshots. This walks one commit per day, oldest first, so the newest
details for each racquet win, then folds in whatever models.json already has.
Safe to re-run.

    python3 tools/backfill_models.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tw_used  # noqa: E402


def git(*args):
    return subprocess.run(["git", *args], cwd=tw_used.HERE, capture_output=True,
                          text=True, check=True).stdout


def main():
    log = git("log", "--reverse", "--format=%h %ad", "--date=short", "--", "snapshot.json")
    last_per_day = {}
    for line in log.splitlines():
        h, day = line.split()
        last_per_day[day] = h                     # later commits overwrite earlier
    models = {}
    for day, h in sorted(last_per_day.items()):
        snap = json.loads(git("show", f"{h}:snapshot.json"))
        listings = snap["listings"] if isinstance(snap, dict) else snap
        for r in listings:
            if r.get("code"):
                models[r["racquet"]] = {"code": r["code"], "specs": r.get("specs") or {},
                                        "nspec": r.get("nspec") or {}}
    models.update(tw_used.load_models())          # anything newer on disk wins
    with open(tw_used.MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(models.items())), f, indent=1, ensure_ascii=False)
    print(f"{len(models)} racquets from {len(last_per_day)} days of snapshots")


if __name__ == "__main__":
    main()
