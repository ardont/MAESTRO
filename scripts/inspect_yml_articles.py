import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

for a in articles:
    if a.get("staticId") in [213875, 213873, 214357, 214363]:
        print(f"\n=== staticId: {a.get('staticId')} | Title: {a.get('title')} ===")
        print(a.get("html_content"))
