"""Behavior facts for the motive analysis of one person (no network calls).

Usage: [TZ_OFFSET=-8] [AS_OF=YYYY-MM-DD] python3 -I motive_stats.py <person_dir> <handle> > stats.txt
person_dir: out/deep/<handle> with posts.json, comments.json, threads.json (written by deep.py).
TZ_OFFSET: the person's UTC offset in hours, used for time-of-day (default -8, US Pacific).

Prints sections A–J. They are facts for the analyst, not conclusions:
  A basics · B timeline of originals · C what performs · D keyword signals (monetization / job / creator / side project)
  E when they post · F commenting on others (volume, speed, targets, which targets engage back)
  G their replies under own posts · H reply window (replies by how long after posting a comment arrived)
  I early regulars (arrive within ~1h on several posts — check reciprocity before calling them relationships)
  J late comments without a reply from the person (candidate real readers)
"""
import json, os, re, sys, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

D, H = sys.argv[1], sys.argv[2].lower()
TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET", "-8"))))
P = json.load(open(os.path.join(D, "posts.json")))
C = json.load(open(os.path.join(D, "comments.json")))
T = json.load(open(os.path.join(D, "threads.json"))) if os.path.exists(os.path.join(D, "threads.json")) else {}


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def pdate(p):
    return ts(((p.get("postedAt") or {}).get("date")) or "")


def is_own(p):
    return ((p.get("author") or {}).get("publicIdentifier") or "").lower() == H and \
        "repost" not in (((p.get("header") or {}).get("text")) or "").lower()


def one(s, n):
    return (s or "").replace("\n", " ").strip()[:n]


origs = sorted([p for p in P if is_own(p) and pdate(p)], key=pdate)
me_ids = {(p.get("author") or {}).get("id") for p in origs} - {None}
AS_OF = ts(os.environ["AS_OF"] + "T23:59:59+00:00") if os.environ.get("AS_OF") else \
    max([pdate(p) for p in P if pdate(p)] + [ts(c["createdAt"]) for c in C if ts(c.get("createdAt") or "")])


def is_me(actor):
    a = actor or {}
    return a.get("id") in me_ids or (a.get("linkedinUrl") or "").rstrip("/").lower().endswith("/" + H)


eng = lambda x: x.get("engagement") or {}

print("== A. 基本面")
print("自我介绍:", next(((p.get("author") or {}).get("info") for p in origs), ""))
print(f"帖子 {len(P)} 条（原创 {len(origs)}，转发 {len(P) - len(origs)}），原创时间 {pdate(origs[0]).date() if origs else '-'} ~ {pdate(origs[-1]).date() if origs else '-'}")
print(f"本人评论 {len(C)} 条，时间 {min(c['createdAt'] for c in C)[:10] if C else '-'} ~ {max(c['createdAt'] for c in C)[:10] if C else '-'}"
      "（只抓到这一段，之前的回复看不到）")
FOL = re.compile(r"[^.\n]{0,80}\b\d[\d,.]*\s*[kK]?\+?\s*(followers|subscribers|impressions|views)[^.\n]{0,60}", re.I)
for c in C:
    for m in FOL.finditer(c.get("commentary") or ""):
        print("  本人评论里提到数字:", c["createdAt"][:10], "|", one(m.group(0), 160), "|", c["linkedinUrl"])
for p in origs:
    for m in FOL.finditer(p.get("content") or ""):
        print("  本人帖子里提到数字:", pdate(p).date(), "|", one(m.group(0), 160), "|", p["linkedinUrl"])

print("\n== B. 原创时间线（日期 | 赞 评 转 | 首行）与按月统计")
for p in origs:
    e = eng(p)
    print(f"{pdate(p).date()} | {e.get('likes', 0):>4} {e.get('comments', 0):>3} {e.get('shares', 0):>2} | {one((p.get('content') or '').split(chr(10))[0], 90)}")
by_m = defaultdict(list)
for p in origs:
    by_m[pdate(p).strftime("%Y-%m")].append(eng(p))
print("月份 条数 平均赞 平均评")
for k in sorted(by_m):
    v = by_m[k]
    print(k, len(v), round(sum(x.get("likes", 0) for x in v) / len(v), 1), round(sum(x.get("comments", 0) for x in v) / len(v), 1))

print("\n== C. 什么内容效果好 / 差（按赞数）")
srt = sorted(origs, key=lambda p: eng(p).get("likes", 0), reverse=True)
for tag, lst in (("最高", srt[:8]), ("最低", srt[-8:])):
    for p in lst:
        print(f"{tag} {eng(p).get('likes', 0):>4}赞 {eng(p).get('comments', 0):>3}评 {pdate(p).date()} | {one(p.get('content'), 80)} | {p['linkedinUrl']}")

print("\n== D. 关键词信号（只是线索，要读原文判断是在说自己还是在教读者）")
SIG = {
    "变现": r"newsletter|substack|\bcourse\b|cohort|coaching|mentor(ing)?|1:1|book a (call|session)|calendly|topmate|\bdm me\b|waitlist|consult(ing)?|link (is )?in (the )?(first )?comment|ebook|paid",
    "求职/变动": r"open to work|next chapter|new role|i('ve| have) joined|i('m| am) (leaving|joining)|laid off|layoff|job search|looking for (my|a) next|last day",
    "创作者身份": r"follow (me )?for|top voice|speaker|creator|my series|\bseries\b|subscribe",
    "副业/创业": r"side (project|hustle)|my startup|building (my|a) (own )?(product|company|app)|solo builder|founder",
}
for k, pat in SIG.items():
    hits = [(pdate(p).date(), m, p) for p in origs for m in re.finditer(pat, p.get("content") or "", re.I)]
    print(f"[{k}] 命中 {len(hits)} 处，涉及 {len({id(h[2]) for h in hits})} 条帖子")
    seen = set()
    for d_, m, p in hits:
        if id(p) in seen:
            continue
        seen.add(id(p))
        t = p.get("content") or ""
        print(f"   {d_} …{one(t[max(0, m.start() - 70):m.end() + 70], 170)}… | {p['linkedinUrl']}")

print("\n== E. 发帖时间（本人当地时间）")
print(Counter(pdate(p).astimezone(TZ).strftime("%a %H时") for p in origs).most_common(12))

print("\n== F. 在别人帖下评论")
mine_post = lambda c: (((c.get("post") or {}).get("author") or {}).get("publicIdentifier") or "").lower() == H
others = sorted([c for c in C if not mine_post(c)], key=lambda c: c["createdAt"])
own_c = [c for c in C if mine_post(c)]
print(f"别人帖下 {len(others)} 条，自己帖下 {len(own_c)} 条")
if others:
    day = Counter(c["createdAt"][:10] for c in others)
    print("每天条数:", dict(sorted(day.items())))
    print("时段（当地）:", sorted(Counter(ts(c["createdAt"]).astimezone(TZ).strftime("%a %H时") for c in others).items()))
    t_ = [ts(c["createdAt"]) for c in others]
    gaps = [(b - a).total_seconds() for a, b in zip(t_, t_[1:])]
    lens = sorted(len(c.get("commentary") or "") for c in others)
    print(f"相邻两条间隔≤90秒: {sum(1 for g in gaps if g <= 90)}/{len(gaps)}；评论字符数中位 {lens[len(lens) // 2]}")
    lk = [eng(c.get("post") or {}).get("likes", 0) for c in others]
    print(f"评论落在 ≥500 赞帖下 {sum(1 for x in lk if x >= 500)} 条，100–499 赞 {sum(1 for x in lk if 100 <= x < 500)} 条，<100 赞 {sum(1 for x in lk if x < 100)} 条")
    came = set()
    for lst in T.values():
        for x in lst:
            a = x.get("actor") or {}
            came.add(a.get("id"))
            came.add((a.get("name") or "").lower())
    tgt = defaultdict(lambda: {"n": 0, "answered": 0, "likes": 0})
    info = {}
    for c in others:
        a = (c.get("post") or {}).get("author") or {}
        k = a.get("publicIdentifier") or a.get("name")
        tgt[k]["n"] += 1
        tgt[k]["answered"] += 1 if eng(c).get("comments", 0) > 0 else 0
        tgt[k]["likes"] = max(tgt[k]["likes"], eng(c.get("post") or {}).get("likes", 0))
        info[k] = (a.get("name"), one(a.get("info"), 80), a.get("id") in came or (a.get("name") or "").lower() in came)
    print(f"评论对象 {len(tgt)} 人。下表：本人评论条数 | 其中下面有人接话的条数 | 对方帖子最高赞 | 对方来过本人高讨论帖 | 名字 | 自我介绍")
    for k, v in sorted(tgt.items(), key=lambda kv: kv[1]["n"], reverse=True)[:40]:
        print(f"  {v['n']:>2} | {v['answered']:>2} | {v['likes']:>5} | {'来过' if info[k][2] else '  - '} | {info[k][0]} | {info[k][1]}")

print("\n== G. 本人在自己帖下的回复")
PARENT = re.compile(r"commentUrn=urn%3Ali%3Acomment%3A%28(?:activity|ugcPost)%3A\d+%2C(\d+)%29")
replied = set()
for c in own_c:
    m = PARENT.search(c.get("linkedinUrl") or "")
    if m and "replyUrn" in (c.get("linkedinUrl") or ""):
        replied.add(m.group(1))
names = {x["id"]: (x.get("actor") or {}).get("name") for lst in T.values() for x in lst}
for c in sorted(own_c, key=lambda c: c["createdAt"]):
    m = PARENT.search(c.get("linkedinUrl") or "")
    to = names.get(m.group(1)) if m and "replyUrn" in c["linkedinUrl"] else "(不是回复)"
    print(f"{ts(c['createdAt']).astimezone(TZ).strftime('%m-%d %a %H:%M')} 回 {to} | {one(c.get('commentary'), 130)}")
first_mine = min((ts(c["createdAt"]) for c in C), default=None)

print("\n== H. 回复时间窗口：留言在发帖后多久到、下面有没有回复")
print("标记：本人回=数据里能确认是本人回的；有回复?=下面有回复但早于本人评论数据的起点，多半是本人但无法确认；"
      "别人回=在本人评论数据范围内、但不是本人回的；无=0 回复")
by_url = {p.get("linkedinUrl"): p for p in P}
agg = Counter()
for url, lst in T.items():
    p = by_url.get(url)
    t0 = pdate(p) if p else None
    if not t0:
        m = re.search(r"activity-(\d{19})", url)
        t0 = datetime.fromtimestamp((int(m.group(1)) >> 22) / 1000, timezone.utc) if m else None
    if not t0:
        continue
    live = (AS_OF - t0).total_seconds() < 48 * 3600
    print(f"\n# {t0.astimezone(TZ).strftime('%m-%d %a %H:%M')} {'（发帖不到 48 小时，进行中，不计入汇总）' if live else ''} | {url}")
    for x in sorted(lst, key=lambda x: x["createdAt"]):
        a = x.get("actor") or {}
        if is_me(a):
            continue
        hrs = (ts(x["createdAt"]) - t0).total_seconds() / 3600
        n = eng(x).get("comments", 0)
        if x["id"] in replied:
            flag = "本人回"
        elif n and first_mine and ts(x["createdAt"]) < first_mine:
            flag = "有回复?"
        elif n:
            flag = "别人回"
        else:
            flag = "无"
        if not live:
            b = "≤24h" if hrs <= 24 else ">24h"
            agg[(b, "total")] += 1
            agg[(b, "replied")] += 1 if flag in ("本人回", "有回复?") else 0
        print(f"   +{hrs:6.1f}h {flag:4} | {a.get('name')} | {one(a.get('position'), 60)} | {one(x.get('commentary'), 110)}")
for b in ("≤24h", ">24h"):
    if agg[(b, "total")]:
        print(f"汇总 {b}: {agg[(b, 'total')]} 条，有回复（本人回 + 有回复?）{agg[(b, 'replied')]} 条")
print("提醒：个人生活帖（家人、喜事等）的回复规律常不同，汇总前请人工剔除；有些留言是在 @ 别人，不是对本人说的。")

print("\n== I. 早到常客（在 ≥2 条帖下、发帖后 1 小时内到）——先查是不是互评小组，再决定算不算关系")
arr = defaultdict(list)
sample = {}
for url, lst in T.items():
    p = by_url.get(url)
    t0 = pdate(p) if p else None
    if not t0:
        continue
    for x in lst:
        a = x.get("actor") or {}
        if is_me(a):
            continue
        arr[a.get("name")].append(((ts(x["createdAt"]) - t0).total_seconds() / 3600, url))
        sample[a.get("name")] = (one(a.get("position"), 70), one(x.get("commentary"), 120), len(x.get("commentary") or ""))
visited = Counter(((c.get("post") or {}).get("author") or {}).get("name") for c in others)
for n, v in sorted(arr.items(), key=lambda kv: len(kv[1]), reverse=True):
    posts_n = len({u for _, u in v})
    med = statistics.median(h for h, _ in v)
    if posts_n >= 2 and med <= 1.0:
        print(f"  {n} | 出现在 {posts_n} 条帖下，到达中位 {med:.1f}h | 本人去过对方帖下 {visited.get(n, 0)} 次 | {sample[n][0]} | 例：{sample[n][1]}")

print("\n== J. 晚到（>24h）且没回复的留言——候选'真读者'，逐条读原文判断")
for url, lst in T.items():
    p = by_url.get(url)
    t0 = pdate(p) if p else None
    if not t0:
        continue
    for x in lst:
        a = x.get("actor") or {}
        if is_me(a) or x["id"] in replied or eng(x).get("comments", 0):
            continue
        hrs = (ts(x["createdAt"]) - t0).total_seconds() / 3600
        if hrs > 24 and len(x.get("commentary") or "") >= 60:
            print(f"  +{hrs:.0f}h | {a.get('name')} | {one(a.get('position'), 80)} | {one(x.get('commentary'), 240)} | {x.get('linkedinUrl')}")
