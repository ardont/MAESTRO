import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}

# 1. Test GraphQL search or contentPage query
gql_url = "https://zakupki.mos.ru/cms/api/graphql"
q1 = """
{
  contentPage(first: 5, where: { displayText_contains: "поставщик" }) {
    contentItemId
    displayText
    content { html }
  }
}
"""
try:
    r = httpx.post(gql_url, json={"query": q1}, headers=headers, timeout=10.0, verify=False)
    print("GraphQL search test status:", r.status_code)
    print("GraphQL search response:", r.text[:400])
except Exception as e:
    print("GraphQL error:", e)

# 2. Test newapi search endpoints
search_endpoints = [
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/Search?query=котировочная+сессия",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/SearchArticles?query=котировочная+сессия",
    "https://zakupki.mos.ru/newapi/api/KnowledgeBase/SearchArticles?searchString=котировочная+сессия",
    "https://zakupki.mos.ru/newapi/api/Search/Search?query=котировочная+сессия",
]
with httpx.Client(headers=headers, verify=False, timeout=10.0) as client:
    for ep in search_endpoints:
        try:
            r = client.get(ep)
            print(f"Endpoint {ep} -> {r.status_code}")
            if r.status_code == 200:
                print("   Body:", r.text[:200])
        except Exception as e:
            print(f"Endpoint {ep} error: {e}")
