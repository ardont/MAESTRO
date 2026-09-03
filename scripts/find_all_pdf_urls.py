import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import re

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

all_docs = set()
for a in articles:
    text = str(a)
    matches = re.findall(r'https?://[^\s"\'<>]+\.(?:pdf|docx|doc|xlsx|zip)', text, re.IGNORECASE)
    all_docs.update(matches)

print(f"Found {len(all_docs)} unique doc URLs in kb_all_articles.json:")
for u in sorted(all_docs):
    print(" ", u)
