"""Check that every URL in a written Markdown file appears in the fetched raw data.

Usage: python3 -I verify_links.py <file.md> <data_dir> [<data_dir> ...]
data_dir: any folder holding fetched .json / digest.md files (e.g. out/deep/<handle>, or out/deep).
Prints each link that cannot be found; exit code 1 if any.
"""
import os, re, sys

md, dirs = sys.argv[1], sys.argv[2:]
parts = []
for d in dirs:
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            if (f.endswith(".json") or f == "digest.md") and os.path.abspath(p) != os.path.abspath(md):
                parts.append(open(p, encoding="utf-8", errors="replace").read())
corpus = "\n".join(parts).replace("\\/", "/").replace("&amp;", "&")
URL = re.compile(r"https?://[^\s)\]>\"'，。、|（）]+")
text = open(md, encoding="utf-8").read().replace("&amp;", "&")
urls = sorted(set(u.rstrip(".,;:") for u in URL.findall(text)))
bad = [u for u in urls if u not in corpus and u.split("?")[0] not in corpus]
print(f"{os.path.basename(md)}: {len(urls)} links, {len(bad)} not found in raw data")
for u in bad:
    print("   ✗", u)
sys.exit(1 if bad else 0)
