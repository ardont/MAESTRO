import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
from collections import Counter

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

empty = [a for a in articles if not (a.get("html_content") or "").strip()]
print(f"Total empty articles: {len(empty)}")

sections = Counter(a.get("section") for a in empty)
categories = Counter(a.get("category") for a in empty)
services = Counter(a.get("service") for a in empty)

print("\nEmpty articles by section:")
for k, v in sections.items():
    print(f"  {k}: {v}")

print("\nEmpty articles by category:")
for k, v in categories.most_common(10):
    print(f"  {k}: {v}")

print("\nEmpty articles by service:")
for k, v in services.most_common(10):
    print(f"  {k}: {v}")

print("\nAll 193 titles:")
for i, a in enumerate(empty, 1):
    print(f"{i:3d}. [{a.get('section')}|{a.get('category')}] {a.get('title')} (staticId={a.get('staticId')})")
