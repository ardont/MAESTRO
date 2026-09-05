import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import re

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

cms_docs = set()
for a in articles:
    text = str(a)
    matches = re.findall(r'https?://[^\s"\'<>]*(?:cms/media|cms/Media)/[^\s"\'<>]+\.[a-zA-Z0-9]+', text, re.IGNORECASE)
    cms_docs.update(matches)

print(f"Found {len(cms_docs)} CMS media docs in kb_all_articles.json:")
for d in sorted(cms_docs):
    print(" ", d)
