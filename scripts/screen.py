"""Screen LinkedIn connections for recent activity via TREG.

Usage: TREG_API_KEY=... [POSTS_ONLY=1] [ONLY_HANDLES=<file>] [WORKERS=8] [LIMIT=n] [AS_OF=YYYY-MM-DD] \
       python3 -I screen.py <Connections.csv> <out_dir>
POSTS_ONLY=1: only fetch posts (cheap first pass). ONLY_HANDLES: file with one handle per line;
only those contacts are processed (use it to backfill comments for shortlisted people).
Writes raw JSON per contact under out_dir/raw/ and a summary out_dir/screen.csv.
Resumable: contacts with both raw files present are skipped.
"""
import csv, io, json, os, sys, time, threading, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

KEY = os.environ["TREG_API_KEY"]
CSV_PATH, OUT = sys.argv[1], sys.argv[2]
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
NOW = datetime.fromisoformat(os.environ["AS_OF"]).replace(tzinfo=timezone.utc) if os.environ.get("AS_OF") else datetime.now(timezone.utc)
D30 = NOW - timedelta(days=30)

lock = threading.Lock()
spent_micro = 0
done = 0


def handle_of(url):
    path = urllib.parse.urlparse(url).path.strip("/")
    parts = path.split("/")
    return urllib.parse.unquote(parts[1]) if len(parts) > 1 and parts[0] == "in" else path


def call(endpoint, params):
    global spent_micro
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"https://treg.to/call/{endpoint}?{q}", headers={"X-Treg-Token": KEY})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                cost = int(r.headers.get("x-treg-cost-micro") or 0)
                with lock:
                    spent_micro += cost
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            cost = int(e.headers.get("x-treg-cost-micro") or 0) if e.headers else 0
            with lock:
                spent_micro += cost
            body = e.read()[:300].decode("utf-8", "replace")
            last = {"_error": e.code, "_body": body}
            if e.code < 500 and e.code != 429:
                return last
        except Exception as e:  # network / timeout
            last = {"_error": "net", "_body": str(e)[:300]}
        time.sleep(3 * (attempt + 1))
    return last


def parse_date(p):
    try:
        return datetime.fromisoformat(p["postedAt"]["date"].replace("Z", "+00:00"))
    except Exception:
        return None


def summarize(row, posts, comments):
    h = handle_of(row["URL"])
    orig30 = rep30 = 0
    last_orig = None
    likes30 = cmts30 = 0
    for p in (posts or {}).get("elements") or []:
        d = parse_date(p)
        hdr = ((p.get("header") or {}).get("text") or "").lower()
        author = (p.get("author") or {}).get("publicIdentifier")
        is_repost = "repost" in hdr or (author and author.lower() != h.lower())
        if not is_repost and d and (last_orig is None or d > last_orig):
            last_orig = d
        if d and d >= D30:
            if is_repost:
                rep30 += 1
            else:
                orig30 += 1
                e = p.get("engagement") or {}
                likes30 += int(e.get("likes") or 0)
                cmts30 += int(e.get("comments") or 0)
    com30 = 0
    for c in (comments or {}).get("elements") or []:
        try:
            d = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))
        except Exception:
            d = None
        if d and d >= D30:
            com30 += 1
    return {
        "handle": h, "name": f'{row["First Name"]} {row["Last Name"]}'.strip(),
        "company": row["Company"], "position": row["Position"], "connected_on": row["Connected On"],
        "url": row["URL"],
        "orig_30d": orig30, "reposts_30d": rep30, "comments_30d": com30,
        "likes_on_orig_30d": likes30, "comments_on_orig_30d": cmts30,
        "last_original": last_orig.date().isoformat() if last_orig else "",
        "posts_error": (posts or {}).get("_error", ""), "comments_error": (comments or {}).get("_error", ""),
    }


def work(row):
    global done
    h = handle_of(row["URL"])
    safe = urllib.parse.quote(h, safe="")
    pf, cf = os.path.join(RAW, f"{safe}.posts.json"), os.path.join(RAW, f"{safe}.comments.json")
    if os.path.exists(pf):
        posts = json.load(open(pf))
    else:
        posts = call("harvestapi.linkedin.user.posts", {"profile": row["URL"], "postedLimit": "month"})
        if posts and "_error" not in posts:
            json.dump(posts, open(pf, "w"))
    if os.path.exists(cf):
        comments = json.load(open(cf))
    elif os.environ.get("POSTS_ONLY"):
        comments = None
    else:
        comments = call("harvestapi.linkedin.user.comments", {"profile": row["URL"], "postedLimit": "month"})
        if comments and "_error" not in comments:
            json.dump(comments, open(cf, "w"))
    s = summarize(row, posts, comments)
    with lock:
        done += 1
        if done % 50 == 0:
            print(f"{done} done, spent ${spent_micro/1e6:.2f}", flush=True)
    return s


def main():
    raw = open(CSV_PATH, encoding="utf-8").read().splitlines()
    start = next(i for i, l in enumerate(raw) if l.startswith("First Name"))
    rows = [r for r in csv.DictReader(io.StringIO("\n".join(raw[start:]))) if r.get("URL", "").strip()]
    only = os.environ.get("ONLY_HANDLES")
    if only:
        keep = {l.strip().lower() for l in open(only) if l.strip()}
        rows = [r for r in rows if handle_of(r["URL"]).lower() in keep]
    limit = int(os.environ.get("LIMIT", "0") or 0)
    if limit:
        rows = rows[:limit]
    print(f"screening {len(rows)} contacts", flush=True)
    out = []
    with ThreadPoolExecutor(max_workers=int(os.environ.get("WORKERS", "8"))) as ex:
        for f in as_completed([ex.submit(work, r) for r in rows]):
            out.append(f.result())
    out.sort(key=lambda s: (s["orig_30d"] * 2 + s["comments_30d"], s["reposts_30d"]), reverse=True)
    with open(os.path.join(OUT, "screen.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    errs = sum(1 for s in out if s["posts_error"] or s["comments_error"])
    print(f"finished {len(out)}; errors {errs}; spent ${spent_micro/1e6:.2f}", flush=True)


main()
