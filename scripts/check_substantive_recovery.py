import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json
from bs4 import BeautifulSoup

url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesPreview"
r = httpx.get(url, params={"query": json.dumps({"filter": {}})}, verify=False, timeout=30)
items = r.json().get("items", [])
prev_by_static_id = {it.get("staticId"): it for it in items if it.get("staticId")}

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    orig = json.load(f)

empty_orig = [a for a in orig if not (a.get("html_content") or "").strip()]

has_real_text = []
short_or_empty_text = []

for a in empty_orig:
    sid = a.get("staticId")
    it = prev_by_static_id.get(sid)
    raw_html = it.get("previewText", "") if it else ""
    soup = BeautifulSoup(raw_html, "html.parser")
    clean_text = soup.get_text(strip=True)
    if len(clean_text) > 30:
        has_real_text.append((a, clean_text))
    else:
        short_or_empty_text.append((a, raw_html))

print(f"Empty articles total: {len(empty_orig)}")
print(f"Articles with substantive recovered text (>30 chars): {len(has_real_text)}")
print(f"Articles still short/empty (<30 chars): {len(short_or_empty_text)}")

print("\nShort/empty sample:")
for a, raw in short_or_empty_text[:15]:
    print(f"  title='{a.get('title')}' | staticId={a.get('staticId')} | raw='{raw}'")
