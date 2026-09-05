import sys
import json
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

for a in articles:
    if a.get("staticId") == 213911:
        print("=== staticId: 213911 ===")
        print("Title:", a.get("title"))
        print("HTML Content:")
        print(a.get("html_content"))
