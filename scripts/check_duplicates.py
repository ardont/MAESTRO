import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
from collections import defaultdict

with open('dataset/kb_all_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

# Group by title
by_title = defaultdict(list)
for a in articles:
    t = (a.get('title') or '').strip().lower()
    by_title[t].append(a)

duplicates = {t: items for t, items in by_title.items() if len(items) > 1}
print(f"Total unique titles: {len(by_title)}")
print(f"Titles appearing multiple times: {len(duplicates)}")

empty = [a for a in articles if not (a.get('html_content') or '').strip()]
print(f"Total empty articles: {len(empty)}")

recoverable_from_other_instance = 0
for a in empty:
    t = (a.get('title') or '').strip().lower()
    matches = by_title[t]
    has_non_empty = any((m.get('html_content') or '').strip() for m in matches)
    if has_non_empty:
        recoverable_from_other_instance += 1

print(f"Empty articles that have a NON-EMPTY version with the same title: {recoverable_from_other_instance}")

# Let's inspect some duplicate examples
for t, items in list(duplicates.items())[:10]:
    print(f"\nTitle: '{items[0].get('title')}'")
    for it in items:
        hl = len(it.get('html_content') or '')
        print(f"   id={it.get('id')}, staticId={it.get('staticId')}, section={it.get('section')}, html_len={hl}")
