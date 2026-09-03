import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re

with open("sandbox/main.js", "r", encoding="utf-8") as f:
    js = f.read()

for target in ["QuerySmartSearch", "GetArticlesPreview", "GetServicesBySectionType", "GetEntity", "details/:system"]:
    print(f"\n==================== TARGET: {target} ====================")
    for m in re.finditer(re.escape(target), js):
        idx = m.start()
        start = max(0, idx - 250)
        end = min(len(js), idx + 250)
        print("--- SNIPPET ---")
        print(js[start:end])
