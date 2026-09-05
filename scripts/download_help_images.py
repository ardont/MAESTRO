import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import re
import os
import httpx
from urllib.parse import unquote

with open("dataset/kb_clean.json", "r", encoding="utf-8") as f:
    clean = json.load(f)

img_pattern = re.compile(r'!\[(.*?)\]\((https?://help\.mos\.ru/uploads/[^\)]+)\)')
# Note: we need to match until the actual end of URL even with parentheses!
# In HTML it was <img src="https://help.mos.ru/uploads/risynok1(15).png" />

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

images_dir = "dataset/images"
os.makedirs(images_dir, exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0"}
downloaded = 0
failed = 0

with httpx.Client(headers=headers, verify=False, follow_redirects=True, timeout=15) as client:
    for a in articles:
        html = a.get("html_content") or ""
        # Find all help.mos.ru image URLs in html
        urls = re.findall(r'src=[\'"](https?://help\.mos\.ru/uploads/[^\'"]+)[\'"]', html)
        for u in set(urls):
            filename = os.path.basename(u)
            safe_name = "".join(c for c in f"help_{filename}" if c.isalnum() or c in ('.', '_', '-', '(', ')'))
            local_path = os.path.join(images_dir, safe_name)
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                try:
                    r = client.get(u)
                    if r.status_code == 200 and len(r.content) > 1000:
                        with open(local_path, "wb") as img_f:
                            img_f.write(r.content)
                        downloaded += 1
                        print(f"Downloaded: {safe_name} ({len(r.content):,} bytes)")
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    print(f"Error {u}: {e}")

print(f"Total downloaded help.mos.ru images: {downloaded}, failed: {failed}")
