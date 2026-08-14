import requests
from bs4 import BeautifulSoup
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url = "https://www.roseltorg.ru/knowledge_db/registration/article/eis"
r = requests.get(url, headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

debug_info = {}
debug_info["title"] = soup.title.get_text(strip=True) if soup.title else ""
debug_info["h1"] = [h.get_text(strip=True) for h in soup.find_all('h1')]

# Find divs with large text or specific classes
divs = []
for d in soup.find_all(['div', 'article', 'section']):
    cls = d.get('class', [])
    text = d.get_text(strip=True)
    if len(text) > 200:
        divs.append({
            "tag": d.name,
            "class": " ".join(cls) if isinstance(cls, list) else str(cls),
            "text_len": len(text),
            "text_sample": text[:150]
        })

debug_info["large_containers"] = sorted(divs, key=lambda x: x["text_len"], reverse=True)[:15]

with open("debug_page.json", "w", encoding="utf-8") as f:
    json.dump(debug_info, f, ensure_ascii=False, indent=2)

print("Saved debug_page.json in UTF-8")
