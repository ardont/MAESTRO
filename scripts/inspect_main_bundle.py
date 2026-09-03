import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import re

url = "https://zakupki.mos.ru/main.a310283558f57e92.js"
print("Downloading main JS...")
try:
    r = httpx.get(url, timeout=30.0, verify=False)
    print("Status:", r.status_code, "Size:", len(r.content))
    text = r.text

    # Search for all mentions of KnowledgeBase or Article
    matches = set(re.findall(r'/[a-zA-Z0-9_/]+(?:KnowledgeBase|Article|Knowledge)[a-zA-Z0-9_/]*', text))
    print(f"\nFound {len(matches)} matches for Knowledge/Article:")
    for m in sorted(matches):
        print(" ", m)

    # Search for details / article routes
    routes = set(re.findall(r'knowledgebase/[a-zA-Z0-9_/:?]+', text, re.IGNORECASE))
    print(f"\nFound {len(routes)} knowledgebase routes:")
    for rt in sorted(routes):
        print(" ", rt)

except Exception as e:
    print("Error:", e)
