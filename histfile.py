"""One reader for history.csv, shared by the scraper and the report.

Every consumer wants the same thing -- the rows as dicts, with the price as a
number and unparseable rows skipped -- so they all come through here. The
result is cached against the file's size and modification time: a run reads
the file once however many functions ask, and a write (a new scrape appended,
a merge de-duplicated) is picked up on the next call.
"""
import csv
import os

_cache = {}


def rows(path, priced=True):
    """history.csv rows as dicts; [] when the file doesn't exist yet.

    priced adds "price" (float) and drops rows whose used_price won't parse.
    With priced=False every row comes back untouched, for rewriting the file.
    Callers must not mutate the returned dicts: they are shared.
    """
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return []
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    if key not in _cache:
        _cache.clear()
        with open(path, newline="", encoding="utf-8") as f:
            raw = list(csv.DictReader(f))
        good = []
        for r in raw:
            try:
                good.append({**r, "price": float(r["used_price"])})
            except (KeyError, TypeError, ValueError):
                continue
        _cache[key] = (raw, good)
    raw, good = _cache[key]
    return good if priced else raw
