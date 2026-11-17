"""Deep-fetch selected LinkedIn contacts via TREG and write readable digests.

Usage: TREG_API_KEY=... [AS_OF=YYYY-MM-DD] [SHALLOW=1] python3 -I deep.py <out_dir> <handle> [<handle> ...]
SHALLOW=1: one page only, no threads/partners, written to out_dir/shallow/<handle>.
Note: comment threads are the first page only (newest 50).
For each handle: up to 4 pages of posts and comments (about 6 months), comment threads
under their 8 most-discussed recent originals, and recent posts of their top 5
interaction partners. Raw JSON goes to out_dir/deep/<handle>/, digest to
out_dir/deep/<handle>/digest.md.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from collections import Counter
from datetime import datetime, timezone, timedelta

KEY = os.environ["TREG_API_KEY"]
OUT = sys.argv[1]
HANDLES = sys.argv[2:]
SHALLOW = bool(os.environ.get("SHALLOW"))
PAGES = 1 if SHALLOW else 4
NOW = datetime.fromisoformat(os.environ["AS_OF"]).replace(tzinfo=timezone.utc) if os.environ.get("AS_OF") else datetime.now(timezone.utc)
SIX_MONTHS = NOW - timedelta(days=183)
spent = 0


def call(endpoint, params):
    global spent
    req = urllib.request.Request(
        f"https://treg.to/call/{endpoint}?{urllib.parse.urlencode(params)}", headers={"X-Treg-Token": KEY})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                spent += int(r.headers.get("x-treg-cost-micro") or 0)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            spent += int((e.headers or {}).get("x-treg-cost-micro") or 0)
            if e.code < 500 and e.code != 429:
                return {"_error": e.code, "elements": []}
        except Exception:
            pass
        time.sleep(4 * (attempt + 1))
    return {"_error": "failed", "elements": []}


def dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def paged(endpoint, base, date_of, pages=None):
    pages = pages or PAGES
    items, token = [], None
    for page in range(1, pages + 1):
        params = dict(base, page=page)
        if token:
            params["paginationToken"] = token
        d = call(endpoint, params)
        el = d.get("elements") or []
        items += el
        token = (d.get("pagination") or {}).get("paginationToken")
        dates = [date_of(x) for x in el if date_of(x)]
        if not el or not token or (dates and min(dates) < SIX_MONTHS):
            break
    return items


def post_date(p):
    return dt(((p.get("postedAt") or {}).get("date")) or "")


def comment_date(c):
    return dt(c.get("createdAt") or "")


def clip(s, n=700):
    s = (s or "").replace("\r", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def run(handle):
    folder = os.path.join(OUT, "shallow" if SHALLOW else "deep", handle)
    os.makedirs(folder, exist_ok=True)
    url = f"https://www.linkedin.com/in/{handle}"
    posts = paged("harvestapi.linkedin.user.posts", {"profile": url}, post_date)
    comments = paged("harvestapi.linkedin.user.comments", {"profile": url}, comment_date)
    json.dump(posts, open(os.path.join(folder, "posts.json"), "w"))
    json.dump(comments, open(os.path.join(folder, "comments.json"), "w"))

    def is_own(p):
        hdr = ((p.get("header") or {}).get("text") or "").lower()
        a = ((p.get("author") or {}).get("publicIdentifier") or "").lower()
        return "repost" not in hdr and a == handle.lower()

    originals = [p for p in posts if is_own(p)]
    recent = [p for p in originals if (post_date(p) or SIX_MONTHS) >= NOW - timedelta(days=90)]
    top = [] if SHALLOW else sorted(recent, key=lambda p: int((p.get("engagement") or {}).get("comments") or 0), reverse=True)[:8]
    threads = {}
    for p in top:
        if int((p.get("engagement") or {}).get("comments") or 0) == 0:
            continue
        d = call("harvestapi.linkedin.post.comments", {"post": p["linkedinUrl"], "sortBy": "date"})
        threads[p["linkedinUrl"]] = d.get("elements") or []
    json.dump(threads, open(os.path.join(folder, "threads.json"), "w"))

    partners = Counter()
    names = {}
    for c in comments:
        a = (c.get("post") or {}).get("author") or {}
        pid = (a.get("publicIdentifier") or "").lower()
        if pid and pid != handle.lower():
            partners[pid] += 1
            names[pid] = a.get("name")
    for els in threads.values():
        for c in els:
            a = c.get("actor") or {}
            pid = urllib.parse.urlparse(a.get("linkedinUrl") or "").path.strip("/").split("/")[-1].lower()
            if pid and pid != handle.lower():
                partners[pid] += 1
                names[pid] = a.get("name")
    partner_posts = {}
    for pid, _ in ([] if SHALLOW else partners.most_common(5)):
        d = call("harvestapi.linkedin.user.posts",
                 {"profile": f"https://www.linkedin.com/in/{pid}", "scrapePostedLimit": "month"})
        partner_posts[pid] = d.get("elements") or []
    json.dump(partner_posts, open(os.path.join(folder, "partners.json"), "w"))

    L = [f"# {handle}", f"profile: {url}", f"fetched {NOW.date()}; posts {len(posts)} (own {len(originals)}), comments {len(comments)}", ""]
    L.append("## Posts and reposts (newest first)")
    for p in posts:
        e = p.get("engagement") or {}
        kind = "OWN" if is_own(p) else f"REPOST of {(p.get('author') or {}).get('name')}"
        d = post_date(p)
        L.append(f"- [{d.date() if d else '?'}] {kind} | likes {e.get('likes')} comments {e.get('comments')} shares {e.get('shares')} | {p.get('linkedinUrl')}")
        L.append(f"  {clip(p.get('content'))}")
    L.append("\n## Comments they wrote (newest first)")
    for c in comments:
        post = c.get("post") or {}
        a = post.get("author") or {}
        d = comment_date(c)
        L.append(f"- [{d.date() if d else '?'}] on post by {a.get('name')} ({a.get('publicIdentifier')}) | {c.get('linkedinUrl')}")
        L.append(f"  POST: {clip(post.get('content'), 300)}")
        L.append(f"  THEIR COMMENT: {clip(c.get('commentary'), 500)}")
    L.append("\n## Comment threads under their most-discussed recent posts")
    for purl, els in threads.items():
        L.append(f"### {purl}")
        for c in els:
            a = c.get("actor") or {}
            d = comment_date(c)
            L.append(f"- [{d.date() if d else '?'}] {a.get('name')} ({a.get('linkedinUrl')}) — {a.get('position') and clip(a.get('position'), 90)}")
            L.append(f"  {clip(c.get('commentary'), 400)}")
    L.append("\n## Top interaction partners and their posts in the last month")
    for pid, n in partners.most_common(5):
        L.append(f"### {names.get(pid)} ({pid}) — {n} interactions")
        for p in partner_posts.get(pid, [])[:15]:
            d = post_date(p)
            e = p.get("engagement") or {}
            L.append(f"- [{d.date() if d else '?'}] likes {e.get('likes')} comments {e.get('comments')} | {p.get('linkedinUrl')}")
            L.append(f"  {clip(p.get('content'), 400)}")
    open(os.path.join(folder, "digest.md"), "w").write("\n".join(L))
    print(f"{handle}: posts {len(posts)}, comments {len(comments)}, threads {len(threads)}, partners {len(partner_posts)}; spent so far ${spent/1e6:.2f}", flush=True)


for h in HANDLES:
    run(h)
print(f"total spent ${spent/1e6:.2f}")
