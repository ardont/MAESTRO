import httpx
import json

url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/QuerySmartSearch"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}

payloads = [
    {"searchString": "котировочная сессия"},
    {"query": "котировочная сессия"},
    {"text": "котировочная сессия"},
    {"filter": {"searchString": "котировочная сессия"}},
    {"searchString": "поставщик", "count": 10},
    {"query": {"searchString": "поставщик"}},
    "котировочная сессия"
]

with httpx.Client(headers=headers, timeout=10.0, verify=False) as client:
    for p in payloads:
        try:
            r = client.post(url, json=p)
            print(f"Payload {p} -> Status: {r.status_code}")
            if r.status_code == 200:
                print("   Response:", r.text[:300])
        except Exception as e:
            print(f"Payload {p} -> Error: {e}")
