import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json
import re

headers = {"User-Agent": "Mozilla/5.0"}
with httpx.Client(headers=headers, verify=False) as c:
    r = c.get(
        "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesPreview",
        params={"query": json.dumps({"filter": {"textPattern": "YML"}})}
    )
    if r.status_code == 200:
        items = r.json().get("items", [])
        for it in items:
            sid = it.get("staticId")
            name = it.get("largeName")
            text = it.get("previewText") or ""
            urls = re.findall(r'href=[\'"]([^\'"]+)[\'"]', text)
            if urls:
                print(f"[{sid}] {name}")
                for u in urls:
                    print(f"   -> {u}")
