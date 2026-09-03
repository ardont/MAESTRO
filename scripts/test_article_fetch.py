import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

urls_to_test = [
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticle?id=576047",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticle?id=171501",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticle?staticId=171501",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticleDetail?id=576047",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticleDetail?staticId=171501",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticleById?id=576047",
    "https://zakupki.mos.ru/knowledgebase/article/171501",
    "https://zakupki.mos.ru/knowledgebase/article/508580",
]

with httpx.Client(headers=headers, verify=False, timeout=10.0, follow_redirects=True) as client:
    for url in urls_to_test:
        try:
            r = client.get(url)
            print(f"URL: {url} -> Status: {r.status_code}, Length: {len(r.text)}, Content-Type: {r.headers.get('content-type')}")
            if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                print("   JSON preview:", r.text[:200])
        except Exception as e:
            print(f"URL: {url} -> Error: {e}")
