import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json

url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesPreview"
r = httpx.get(url, params={"query": json.dumps({"filter": {}})}, verify=False, timeout=30)
items = r.json().get("items", [])
prev_by_static_id = {it.get("staticId"): it for it in items if it.get("staticId")}

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    orig = json.load(f)

empty_orig = [a for a in orig if not (a.get("html_content") or "").strip()]

print(f"Total empty articles to recover: {len(empty_orig)}")
for i, a in enumerate(empty_orig[:5], 1):
    sid = a.get("staticId")
    it = prev_by_static_id.get(sid)
    txt = it.get("previewText", "")
    print(f"\n[{i}] {a.get('title')} (staticId={sid})")
    print(f"    Length: {len(txt)} chars")
    print(f"    Snippet: {txt[:200]}")
