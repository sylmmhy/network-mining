"""Rank screened contacts by how much they interact with other people, and write the priority list.

Usage: python3 -I rank.py <out_dir> <list.md> <list.csv> [--min-orig 4]
Reads <out_dir>/screen.csv and <out_dir>/raw/*.json (written by screen.py).
Writes <out_dir>/ranked.json plus a Markdown and a CSV (utf-8-sig, opens in Excel) priority list.

Score ("来往分") = comments on other people's posts + replies under own posts + min(comments received, 50).
The cap of 50 keeps lead-magnet posts ("comment X and I'll send it") from dominating.
Pure broadcasters (never comment, almost no comments received) are dropped.
Contacts without a comments file are listed so they can be backfilled with screen.py ONLY_HANDLES=...
"""
import csv, json, os, re, sys, urllib.parse
from collections import Counter
from datetime import datetime, timezone, timedelta

OUT, MD, CSV = sys.argv[1], sys.argv[2], sys.argv[3]
MIN_ORIG = int(sys.argv[sys.argv.index("--min-orig") + 1]) if "--min-orig" in sys.argv else 4
AS_OF = datetime.fromisoformat(os.environ["AS_OF"]).replace(tzinfo=timezone.utc) if os.environ.get("AS_OF") else datetime.now(timezone.utc)
D30 = AS_OF - timedelta(days=30)


def dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def raw(h, kind):
    f = os.path.join(OUT, "raw", urllib.parse.quote(h, safe="") + f".{kind}.json")
    return json.load(open(f)).get("elements") or [] if os.path.exists(f) else None


rows = list(csv.DictReader(open(os.path.join(OUT, "screen.csv"), encoding="utf-8")))
res, missing = [], []
for r in rows:
    if int(r["orig_30d"] or 0) < MIN_ORIG:
        continue
    h = r["handle"]
    posts = raw(h, "posts") or []
    headline = next(((p.get("author") or {}).get("info") or "" for p in posts
                     if ((p.get("author") or {}).get("publicIdentifier") or "").lower() == h.lower()), "")
    C = raw(h, "comments")
    if C is None:
        missing.append(h)
        C = []
    others = own_replies = 0
    people = set()
    for c in C:
        d = dt(c.get("createdAt") or "")
        if not d or d < D30:
            continue
        a = (c.get("post") or {}).get("author") or {}
        pid = (a.get("publicIdentifier") or a.get("name") or "").lower()
        if pid == h.lower():
            own_replies += 1
        else:
            others += 1
            people.add(pid)
    recv = int(r["comments_on_orig_30d"] or 0)
    res.append({**r, "headline": headline[:150], "comments_on_others": others, "replies_on_own": own_replies,
                "people_commented": len(people), "comments_received_30d": recv,
                "score": others + own_replies + min(recv, 50), "has_comments": h not in missing})

broadcast = [x for x in res if x["comments_on_others"] == 0 and x["replies_on_own"] == 0 and x["comments_received_30d"] < 5 and x["has_comments"]]
keep = [x for x in res if x not in broadcast]
keep.sort(key=lambda x: (x["score"], x["people_commented"], int(x["orig_30d"])), reverse=True)
json.dump(keep, open(os.path.join(OUT, "ranked.json"), "w"), ensure_ascii=False)


def tier(s):
    return "第一" if s >= 40 else "第二" if s >= 20 else "第三" if s >= 10 else "第四"


def role(x):
    pos = f'{x["position"]} {x["company"]}'
    t = f'{pos} {x["headline"]}'
    F = r"(co-?founder\b|\bfounder\b(?!s)|\bceo\b|\bowner\b)"
    if re.search(r"recruit|talent|sourc", t, re.I): return "招聘"
    if re.search(r"venture|investor|\bvc\b|capital|managing partner|principal", pos, re.I) and not re.search(F, pos, re.I): return "投资人"
    if re.search(F, pos, re.I): return "创始人"
    if re.search(r"venture|investor|\bvc\b|capital", pos, re.I): return "投资人"
    if re.search(r"student|undergrad|intern\b|research fellow", t, re.I): return "学生"
    if re.search(F, x["headline"], re.I): return "创始人"
    return "职员/其他"


out = []
for i, x in enumerate(keep, 1):
    note = []
    if not x["has_comments"]: note.append("缺评论数据，分数偏低")
    if x["comments_received_30d"] >= 500 and x["comments_on_others"] <= 5: note.append("留言可能来自引流帖（推断，需深挖确认）")
    out.append({"排名": i, "优先级": tier(x["score"]), "姓名": x["name"].strip(), "主页": x["url"], "身份": role(x),
                "职位": x["position"], "公司": x["company"], "LinkedIn 自我介绍": x["headline"],
                "30天原创": int(x["orig_30d"]), "评论别人(次)": x["comments_on_others"], "评论过的人数": x["people_commented"],
                "回复自己帖下留言": x["replies_on_own"], "收到留言": x["comments_received_30d"], "来往分": x["score"], "备注": "；".join(note)})
if not out:
    sys.exit("no one passed the threshold")
with open(CSV, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

cnt = {t: sum(1 for r in out if r["优先级"] == t) for t in ("第一", "第二", "第三", "第四")}
roles = Counter(r["身份"] for r in out)
L = [f"# LinkedIn 活跃联系人优先级名单（{AS_OF.date()}）", "",
     "用途：找出最值得帮他们\"从人脉中发现能做的事\"的人，按优先级排序。身份不限。",
     f"数据：{AS_OF.date()} 抓取的 LinkedIn 公开数据，只看最近 30 天（{D30.date()} 至 {AS_OF.date()}）。",
     f"筛选：{len(rows)} 位有主页的联系人里，最近 30 天原创至少 {MIN_ORIG} 条的 {len(res)} 人，去掉 {len(broadcast)} 个纯广播号，共 {len(out)} 人。",
     "排序：按\"来往分\" = 评论别人的次数 + 回复自己帖下留言的次数 + 收到的留言数（最多计 50）。同分时，评论过的不同人越多越靠前。",
     "优先级：" + "，".join(f"{t}（{rng}）{cnt[t]} 人" for t, rng in zip(("第一", "第二", "第三", "第四"), ("来往分 ≥40", "20–39", "10–19", "<10"))) + "。",
     "身份分布（按职位粗分）：" + "、".join(f"{k} {v}" for k, v in roles.most_common()) + "。",
     "说明：评论数据每人只抓一页（最多 50 条），活跃评论者会被少算，深挖时以深挖数字为准。保密：只在内部看，不外发。", ""]
for t in ("第一", "第二", "第三", "第四"):
    L += [f"## {t}优先（{cnt[t]} 人）", "",
          "| # | 姓名 | 身份 | 职位 @ 公司 | 30天原创 | 评论别人（次/人） | 回复自己帖下 | 收到留言 | 备注 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in out:
        if r["优先级"] == t:
            pos = f'{r["职位"]} @ {r["公司"]}'.strip(" @").replace("|", "/")
            L.append(f'| {r["排名"]} | [{r["姓名"]}]({r["主页"]}) | {r["身份"]} | {pos} | {r["30天原创"]} | '
                     f'{r["评论别人(次)"]}/{r["评论过的人数"]} | {r["回复自己帖下留言"]} | {r["收到留言"]} | {r["备注"]} |')
    L.append("")
open(MD, "w", encoding="utf-8").write("\n".join(L))
print(f"30天原创>={MIN_ORIG}: {len(res)} | 纯广播号: {len(broadcast)} | 留下: {len(out)} | 缺评论数据: {len(missing)}")
print("优先级:", cnt, "| 身份:", roles.most_common())
if missing:
    mf = os.path.join(OUT, "need_comments.txt")
    open(mf, "w").write("\n".join(missing))
    print(f"缺评论数据的 {len(missing)} 人已写入 {mf}，可用 screen.py 的 ONLY_HANDLES 补抓后重跑本脚本")
for r in out[:25]:
    print(r["排名"], r["优先级"], r["姓名"], "|", r["身份"], "|", r["来往分"], "|", r["备注"])
