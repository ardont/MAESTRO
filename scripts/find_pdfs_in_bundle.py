import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re

with open("sandbox/main.js", "r", encoding="utf-8") as f:
    js = f.read()

pdfs = set(re.findall(r'[^"\'`\s\(\)]+\.pdf', js, re.IGNORECASE))
print(f"Found {len(pdfs)} PDF references in main.js:")
for p in sorted(pdfs):
    print(" ", p)
