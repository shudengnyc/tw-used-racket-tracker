#!/usr/bin/env python3
"""Track used-racquet prices at Tennis Warehouse, with price history.

The used catalog page shows only NEW prices; actual used prices live on each
racquet's /orderusedproduct.html page. Both are plain server-rendered HTML, so
we fetch the catalog once for the racquet list, then one page per racquet for
its individual used listings (grade, grip size, price, stock).

Every run appends to history.csv. Once a few weeks of data exist, each listing
is judged against that racquet+grade's OWN past prices rather than one blunt
threshold -- so "cheap" means cheap for that frame, not cheap in the abstract.

Usage:
    python3 tw_used.py                     # full report
    python3 tw_used.py --deals             # only new listings + notable prices
    python3 tw_used.py --brands Wilson Yonex
    python3 tw_used.py --max-price 150 --grip "4 3/8"
    python3 tw_used.py --trend "Blade 98"  # price history for one racquet
"""

import argparse
import concurrent.futures as cf
import csv
import gzip
import http.client
import datetime as dt
import html
import json
import os
import re
import ssl
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request

BASE = "https://www.tennis-warehouse.com"
CATALOG = f"{BASE}/usedcatpage.html?ccode=RACSBYMAKER"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TARGET_BRANDS = ["Wilson", "Yonex", "Tecnifibre", "Head", "Prince", "Solinco"]

# How many past observations before history-based judgements are trustworthy.
MIN_OBS = 3

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "used_prices.csv")     # latest snapshot
HIST_PATH = os.path.join(HERE, "history.csv")        # append-only, all runs
STATE_PATH = os.path.join(HERE, "seen.json")         # for new-listing detection
# used_prices.csv is for reading in a spreadsheet: it stringifies everything and
# stores specs/nspec as Python dict reprs, so it can't be loaded back without
# guessing types. This is the exact round-trip copy the local rebuild reads.
SNAP_PATH = os.path.join(HERE, "snapshot.json")
HTML_PATH = os.path.join(HERE, "report.html")        # standalone clickable report
THUMB_DIR = os.path.join(HERE, "thumbs")             # small, embedded in the page
LARGE_DIR = os.path.join(HERE, "thumbs_large")       # full size, for the lightbox

# Tennis Warehouse resizes on demand. 56px (~2.8KB) is plenty for the 30px row
# thumbnail and gets inlined; 400px (~35KB) backs the click-to-enlarge view and
# is loaded from disk by relative path so it never bloats report.html.
THUMB_URL = "https://img.tennis-warehouse.com/watermark/rs.php?path={code}-thumb.jpg&nw={w}"
THUMB_SIZES = [(THUMB_DIR, 56), (LARGE_DIR, 400)]


def _ssl_context():
    """python.org builds ship without a CA bundle; fall back to the macOS one."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if os.path.exists("/etc/ssl/cert.pem"):
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


# One keep-alive connection per worker thread. The product pages are ~512KB of
# HTML each but gzip to ~45KB, and reusing the socket avoids a TLS handshake per
# racquet -- together roughly a 4x speedup over a fresh urlopen per page.
_local = threading.local()


def _conn(host):
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "host", None) != host:
        if conn is not None:
            conn.close()
        conn = http.client.HTTPSConnection(host, timeout=30, context=SSL_CTX)
        _local.conn, _local.host = conn, host
    return conn


def _drop_conn():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None


def fetch_bytes(url, retries=3):
    parts = urllib.parse.urlsplit(url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    for attempt in range(retries):
        try:
            conn = _conn(parts.netloc)
            conn.request("GET", path, headers={
                "User-Agent": UA,
                "Accept-Encoding": "gzip",
                "Connection": "keep-alive",
            })
            resp = conn.getresponse()
            body = resp.read()                     # must drain to reuse the socket
            if resp.status != 200:
                raise OSError(f"HTTP {resp.status} for {url}")
            if (resp.getheader("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            return body
        except Exception:
            _drop_conn()                           # a stale socket can't be retried
            if attempt == retries - 1:
                raise
            time.sleep(1.0 * (attempt + 1))


def fetch(url, retries=3):
    return fetch_bytes(url, retries).decode("utf-8", "replace")


# --- catalog: one entry per racquet, with its NEW price for reference ---

CELL_RE = re.compile(
    r'data-gtm_impression_code="(?P<code>[^"]*)"\s+'
    r'data-gtm_impression_name="(?P<name>[^"]*)"\s+'
    r'data-gtm_impression_price="(?P<price>[^"]*)"\s+'
    r'data-gtm_impression_brand="(?P<brand>[^"]*)"',
    re.S,
)


# Each catalog cell also carries the list price, star rating and review count.
MSRP_RE = re.compile(r'price-msrp"><span class="is-crossout">\$([\d,.]+)')
RATING_RE = re.compile(r'class="review_agg">([\d.]+)')
NREV_RE = re.compile(r'class="catpage-review_count">(\d+)')
FLAG_RE = re.compile(r'cattable-wrap-cell-info-flag ([a-z_-]+)"')


def _num(text):
    try:
        return float(text.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def get_catalog():
    page = fetch(CATALOG)
    out, seen = [], set()
    cells = list(CELL_RE.finditer(page))
    for i, m in enumerate(cells):
        code = m.group("code")
        if code in seen:
            continue
        seen.add(code)
        # Everything up to the next cell belongs to this racquet.
        end = cells[i + 1].start() if i + 1 < len(cells) else m.end() + 6000
        block = page[m.start():end]
        msrp = MSRP_RE.search(block)
        rating = RATING_RE.search(block)
        nrev = NREV_RE.search(block)
        out.append({
            "code": code,
            "name": html.unescape(m.group("name")),
            "brand": html.unescape(m.group("brand")),
            "new_price": _num(m.group("price")),
            "list_price": _num(msrp.group(1)) if msrp else None,
            "rating": float(rating.group(1)) if rating else None,
            "reviews": int(nrev.group(1)) if nrev else None,
            "flags": sorted(set(FLAG_RE.findall(block))),
        })
    return out


# --- product page: the actual used listings ---

ROW_RE = re.compile(r'<tr data-code="(?P<sku>[^"]+)" class="subproduct.*?</tr>', re.S)
NAME_RE = re.compile(r'<span class="name"><strong>(.*?)</strong>', re.S)
PRICE_RE = re.compile(r'itemprop="price" content="([\d.]+)"')
GRADE_RE = re.compile(r'class="styleitem" data-scode="([^"]*)"')
STOCK_RE = re.compile(r'<span class="available">(\d+)</span>')
GRIP_RE = re.compile(r'(\d+\s+\d+/\d+|4)"\s*\(#(\d)\)')

# The spec table is plain <td><strong>Label:</strong> value</td> rows.
SPEC_RE = re.compile(r'<td class="Specs(?:Lt|Dk)"[^>]*>\s*<strong>\s*([^<:]+?)\s*:?\s*</strong>\s*(.*?)</td>',
                     re.S)
SPEC_KEEP = {
    "Head Size": "head", "Strung Weight": "weight", "Balance": "balance",
    "Swingweight": "swingweight", "Stiffness": "stiffness", "Beam Width": "beam",
    "Composition": "composition", "Power Level": "power",
    "Stroke Style": "stroke", "Swing Speed": "swing", "Grip Type": "griptype",
    "String Tension": "tension", "Length": "length",
}


def numeric_specs(specs):
    """Pull sortable numbers out of the spec strings.

    "98 in² / 632.26 cm²" -> 98 ; "11.9oz / 337g" -> 11.9 and 337 ;
    "12.59in / 31.98cm / 4 pts HL" -> -4 (head-light is negative, so a single
    axis runs head-light to head-heavy).
    """
    n = {}
    if specs.get("head"):
        m = re.search(r"([\d.]+)\s*in", specs["head"])
        if m:
            n["head_in2"] = float(m.group(1))
    if specs.get("weight"):
        m = re.search(r"([\d.]+)\s*oz", specs["weight"])
        if m:
            n["weight_oz"] = float(m.group(1))
        m = re.search(r"([\d.]+)\s*g\b", specs["weight"])
        if m:
            n["weight_g"] = float(m.group(1))
    for key, field in (("swingweight", "swingweight"), ("stiffness", "stiffness")):
        m = re.search(r"([\d.]+)", specs.get(key, ""))
        if m:
            n[field] = float(m.group(1))
    if specs.get("balance"):
        m = re.search(r"([\d.]+)\s*pts\s*(HL|HH)", specs["balance"], re.I)
        if m:
            pts = float(m.group(1))
            n["balance_pts"] = -pts if m.group(2).upper() == "HL" else pts
    return n


def parse_specs(page):
    """Pull the manufacturer spec table into a small flat dict."""
    specs = {}
    for label, value in SPEC_RE.findall(page):
        key = SPEC_KEEP.get(label.strip())
        if not key or key in specs:
            continue
        text = re.sub(r"<[^>]+>", " ", value)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip(" .")
        if text:
            specs[key] = text
    return specs


def get_used_listings(item):
    url = f"{BASE}/orderusedproduct.html?pcode={item['code']}"
    try:
        page = fetch(url)
    except Exception as e:
        print(f"  ! {item['code']}: {e}", file=sys.stderr)
        return []

    specs = parse_specs(page)
    nspec = numeric_specs(specs)
    rows = []
    for m in ROW_RE.finditer(page):
        block = m.group(0)
        price = PRICE_RE.search(block)
        if not price:
            continue
        price = float(price.group(1))
        listing_name = NAME_RE.search(block)
        listing_name = html.unescape(listing_name.group(1)) if listing_name else item["name"]
        grade = GRADE_RE.search(block)
        stock = STOCK_RE.search(block)
        grip = GRIP_RE.search(listing_name)
        new = item["new_price"]
        rows.append({
            "brand": item["brand"],
            "racquet": item["name"],
            "grade": grade.group(1) if grade else "",
            "grip": grip.group(1) + '"' if grip else "",
            "used_price": price,
            "new_price": new,
            "discount_pct": round(100 * (new - price) / new) if new else "",
            # New one is on clearance below the used price -- never buy used here.
            "new_cheaper": bool(new and price >= new),
            "in_stock": int(stock.group(1)) if stock else "",
            "sku": m.group("sku"),
            "code": item["code"],
            "list_price": item.get("list_price"),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
            "specs": specs,
            "nspec": nspec,
            "url": url,
        })
    return rows


def fetch_thumbs(catalog, workers=6):
    """Download any racquet images we don't already have cached, in both sizes."""
    jobs = []
    for folder, width in THUMB_SIZES:
        os.makedirs(folder, exist_ok=True)
        for c in catalog:
            dest = os.path.join(folder, c["code"] + ".jpg")
            if not os.path.exists(dest):
                jobs.append((c["code"], dest, width))
    if not jobs:
        return 0

    def grab(job):
        code, dest, width = job
        try:
            data = fetch_bytes(THUMB_URL.format(code=code, w=width))
            if not data.startswith(b"\xff\xd8"):      # not a JPEG -- skip it
                return 0
            tmp = dest + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            return 1
        except Exception as e:
            print(f"  ! image {code} @{width}px: {e}", file=sys.stderr)
            return 0

    print(f"Fetching {len(jobs)} new racquet images...", file=sys.stderr)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        return sum(ex.map(grab, jobs))


# --- price history -----------------------------------------------------------

HIST_FIELDS = ["date", "brand", "racquet", "grade", "grip", "used_price",
               "new_price", "sku"]


def append_history(listings, today):
    """Append today's listings, skipping anything already recorded today."""
    already = set()
    exists = os.path.exists(HIST_PATH)
    if exists:
        with open(HIST_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["date"] == today:
                    already.add((row["sku"], row["used_price"]))

    with open(HIST_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HIST_FIELDS)
        if not exists:
            w.writeheader()
        for r in listings:
            if (r["sku"], f"{r['used_price']}") in already:
                continue
            w.writerow({
                "date": today,
                "brand": r["brand"],
                "racquet": r["racquet"],
                "grade": r["grade"],
                "grip": r["grip"],
                "used_price": r["used_price"],
                "new_price": r["new_price"] or "",
                "sku": r["sku"],
            })


def load_history(before=None):
    """{(racquet, grade): [prices]} from all runs, optionally excluding today."""
    hist = {}
    if not os.path.exists(HIST_PATH):
        return hist
    with open(HIST_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if before and row["date"] >= before:
                continue
            try:
                price = float(row["used_price"])
            except ValueError:
                continue
            hist.setdefault((row["racquet"], row["grade"]), []).append(price)
    return hist


def judge(row, hist):
    """Rate a listing against its own racquet+grade history."""
    past = hist.get((row["racquet"], row["grade"]), [])
    if len(past) < MIN_OBS:
        return "", None
    low, mid = min(past), statistics.median(past)
    if row["used_price"] < low:
        return "LOWEST EVER", mid
    if row["used_price"] <= mid * 0.9:
        return "BELOW USUAL", mid
    if row["used_price"] >= mid * 1.1:
        return "high", mid
    return "typical", mid


from report import write_html


# --- reporting ---------------------------------------------------------------

def print_table(rows):
    print(f"\n{'USED':>8} {'NEW':>7} {'OFF':>4}  {'GRADE':<8} {'GRIP':<7} "
          f"{'VS HISTORY':<13} RACQUET")
    print("-" * 104)
    for r in rows:
        new = f"${r['new_price']:.0f}" if r["new_price"] else "-"
        off = f"{r['discount_pct']}%" if r["discount_pct"] != "" else "-"
        if r.get("new_cheaper"):
            off = "BUY NEW"
        tag = r.get("verdict") or ("NEW LISTING" if r.get("is_new") else "")
        if r.get("median") and tag in ("LOWEST EVER", "BELOW USUAL", "high"):
            tag = f"{tag} (~${r['median']:.0f})"
        print(f"${r['used_price']:>7.2f} {new:>7} {off:>4}  "
              f"{r['grade'] or '-':<8} {r['grip'] or '-':<7} {tag:<13} {r['racquet']}")


def show_trend(pattern):
    if not os.path.exists(HIST_PATH):
        print("No history yet -- run the scraper a few times first.")
        return
    pat = pattern.lower()
    series = {}
    with open(HIST_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if pat not in row["racquet"].lower():
                continue
            key = (row["racquet"], row["grade"])
            series.setdefault(key, {}).setdefault(row["date"], []).append(
                float(row["used_price"]))
    if not series:
        print(f"No history matching {pattern!r}.")
        return
    for (racquet, grade), by_date in sorted(series.items()):
        prices = [p for ps in by_date.values() for p in ps]
        print(f"\n{racquet} -- {grade or 'ungraded'}")
        print(f"  low ${min(prices):.0f} / median ${statistics.median(prices):.0f} "
              f"/ high ${max(prices):.0f}   ({len(by_date)} days observed)")
        for date in sorted(by_date):
            day = by_date[date]
            print(f"    {date}  ${min(day):.2f}" +
                  (f"  ({len(day)} listed)" if len(day) > 1 else ""))


def _run(cmd, **kw):
    import subprocess
    return subprocess.run(cmd, cwd=HERE, text=True, **kw)


def sync_from_github():
    """Pull down whatever the scheduled run last gathered.

    The scrape happens in CI and nowhere else, so the repo is the single copy
    of history.csv -- this is how it reaches the Mac.
    """
    r = _run(["git", "pull", "--rebase", "--autostash", "--quiet"],
             capture_output=True)
    if r.returncode:
        print("Couldn't sync from GitHub -- showing the local copy.\n"
              f"  {(r.stderr or '').strip()}", file=sys.stderr)
        return False
    return True


def trigger_github_run():
    """Kick off the workflow and wait for it, so --refresh means fresh data."""
    import shutil
    if not shutil.which("gh"):
        print("The gh CLI isn't installed, so I can't start a run.\n"
              "  Install it with:  brew install gh\n"
              "  Or trigger the run from the Actions tab on GitHub.",
              file=sys.stderr)
        return False

    print("Starting a scrape on GitHub...", file=sys.stderr)
    if _run(["gh", "workflow", "run", "check-racquets.yml"],
            capture_output=True).returncode:
        print("Couldn't start the run -- is gh logged in? (gh auth status)",
              file=sys.stderr)
        return False

    # The run needs a moment to exist before it can be watched.
    time.sleep(6)
    rid = _run(["gh", "run", "list", "--workflow", "check-racquets.yml",
                "--limit", "1", "--json", "databaseId",
                "--jq", ".[0].databaseId"], capture_output=True).stdout.strip()
    if not rid:
        print("Started, but couldn't find the run to watch.", file=sys.stderr)
        return False

    print(f"Waiting for run {rid} (about a minute)...", file=sys.stderr)
    if _run(["gh", "run", "watch", rid, "--exit-status", "--interval", "10"],
            capture_output=True).returncode:
        print("The run failed. See:  gh run view " + rid + " --log-failed",
              file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Used racquet prices from Tennis Warehouse. The scrape "
                    "runs on GitHub every 6 hours; by default this just syncs "
                    "the latest results down and shows them.")
    ap.add_argument("--brands", nargs="+", default=TARGET_BRANDS)
    ap.add_argument("--all-brands", action="store_true")
    ap.add_argument("--max-price", type=float)
    ap.add_argument("--min-discount", type=float, default=0)
    ap.add_argument("--grip", help='e.g. "4 3/8"')
    ap.add_argument("--deals", action="store_true",
                    help="only new listings and historically notable prices")
    ap.add_argument("--trend", metavar="RACQUET",
                    help="show recorded price history and exit")
    ap.add_argument("--quiet-if-empty", action="store_true",
                    help="print nothing when no rows match (for scheduled runs)")
    ap.add_argument("--open", action="store_true",
                    help="open the HTML report in the browser when done")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--refresh", action="store_true",
                    help="make GitHub scrape now and wait for it (~1 min), "
                         "instead of showing the last scheduled result")
    ap.add_argument("--scrape", action="store_true",
                    help="scrape Tennis Warehouse from this machine. This is "
                         "what the GitHub job runs; locally it's a fallback "
                         "and its results won't reach the published report "
                         "unless you commit and push them")
    ap.add_argument("--no-sync", action="store_true",
                    help="skip the git pull and use the local copy as-is")
    ap.add_argument("--html-mode", choices=("local", "pages", "artifact"),
                    default="local",
                    help="who the report is built for; 'pages' drops the "
                         "Mac-only Shortcut refresh button (default: local)")
    args = ap.parse_args()

    # One fetch path: GitHub scrapes, everything else reads what it produced.
    if not args.scrape:
        if args.refresh:
            trigger_github_run()          # carry on with the old data if it fails
        if not args.no_sync:
            sync_from_github()

    if args.trend:
        show_trend(args.trend)
        return

    if not args.scrape:
        listings = load_snapshot()
        if listings is None:
            print("No snapshot yet. Get one with:  ./racket --refresh\n"
                  "  (or scrape from this machine with:  ./racket --scrape)",
                  file=sys.stderr)
            return 1
        finish(listings, args)
        return

    catalog = get_catalog()
    if not args.all_brands:
        wanted = {b.lower() for b in args.brands}
        catalog = [c for c in catalog if c["brand"].lower() in wanted]

    print(f"Checking {len(catalog)} racquets...", file=sys.stderr)
    listings = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rows in ex.map(get_used_listings, catalog):
            listings.extend(rows)

    fetch_thumbs(catalog, workers=args.workers)

    if not listings:
        print("No listings returned -- the page layout may have changed.",
              file=sys.stderr)
        return

    today = dt.date.today().isoformat()

    # Judge against history from BEFORE today, then record today's prices.
    hist = load_history(before=today)
    append_history(listings, today)

    previous = set()
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            previous = set(json.load(f))
    key = lambda r: f"{r['sku']}|{r['used_price']}"
    for r in listings:
        r["is_new"] = key(r) not in previous
        r["verdict"], r["median"] = judge(r, hist)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(key(r) for r in listings), f)

    listings.sort(key=lambda r: (-(r["discount_pct"] or 0), r["used_price"]))

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(listings[0].keys()))
        w.writeheader()
        w.writerows(listings)

    with open(SNAP_PATH, "w", encoding="utf-8") as f:
        json.dump(listings, f)

    finish(listings, args)


def load_snapshot():
    """The listing rows exactly as the last scrape produced them, or None."""
    if not os.path.exists(SNAP_PATH):
        return None
    with open(SNAP_PATH, encoding="utf-8") as f:
        return json.load(f)


def finish(listings, args):
    """Filter, write the HTML report, and print -- shared by both paths.

    Filters narrow the printed table only. The HTML report always covers
    everything, since it has its own brand/grade/grip controls built in.
    """
    shown = listings
    if not args.all_brands:
        wanted = {b.lower() for b in args.brands}
        shown = [r for r in shown if r["brand"].lower() in wanted]
    if args.deals:
        shown = [r for r in shown if not r["new_cheaper"]
                 and (r["is_new"] or r["verdict"] in ("LOWEST EVER", "BELOW USUAL"))]
    if args.max_price:
        shown = [r for r in shown if r["used_price"] <= args.max_price]
    if args.min_discount:
        shown = [r for r in shown if (r["discount_pct"] or 0) >= args.min_discount]
    if args.grip:
        shown = [r for r in shown if args.grip in r["grip"]]

    days = len(set(_history_dates()))
    write_html(listings, HTML_PATH, days, HIST_PATH, mode=args.html_mode,
               thumb_dir=THUMB_DIR)

    if args.open:
        import subprocess
        subprocess.run(["open", HTML_PATH], check=False)
        return

    if shown:
        print_table(shown)
    elif not args.quiet_if_empty:
        print("\nNothing matched.")

    print(f"\n{len(listings)} used listings; {sum(r['is_new'] for r in listings)} "
          f"new or repriced since last run; {days} days of history recorded.",
          file=sys.stderr)


def _history_dates():
    if not os.path.exists(HIST_PATH):
        return []
    with open(HIST_PATH, newline="", encoding="utf-8") as f:
        return [row["date"] for row in csv.DictReader(f)]


if __name__ == "__main__":
    main()
