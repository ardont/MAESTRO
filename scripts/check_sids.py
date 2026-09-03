import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json

url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesPreview"
r = httpx.get(url, params={"query": json.dumps({"filter": {}})}, verify=False, timeout=30)
items = r.json().get("items", [])
prev_by_sid = {it.get("staticId"): it for it in items if it.get("staticId")}

test_sids = [508592, 291019, 291024, 291029, 291034, 296336, 296491, 171594]
for sid in test_sids:
    it = prev_by_sid.get(sid)
    if it:
        txt = it.get("previewText") or ""
        print(f"sid={sid}: largeName='{it.get('largeName')}' | preview len={len(txt)}")
        if len(txt) > 0:
            print("   snippet:", txt[:150].replace('\n', ' '))
    else:
        print(f"sid={sid}: NOT in preview items")
