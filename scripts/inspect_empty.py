import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json

with open('dataset/kb_all_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

empty = [a for a in articles if not a.get('html_content') or not a.get('html_content').strip()]
print(f"Total articles: {len(articles)}")
print(f"Empty articles: {len(empty)}")

for i, a in enumerate(empty[:15]):
    print(f"[{i+1}] id={a.get('id')} staticId={a.get('staticId')} section={a.get('section')} cat={a.get('category')} title={a.get('title')} url={a.get('url')}")
    print(f"    keys: {list(a.keys())}")

