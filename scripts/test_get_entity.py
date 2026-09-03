import httpx
import json

tests = [
    "https://zakupki.mos.ru/api/Cssp/Article/GetEntity?id=171501",
    "https://zakupki.mos.ru/api/Cssp/Article/GetEntity?id=508580",
    "https://zakupki.mos.ru/api/Cssp/Article/GetEntity?id=213899",
    "https://zakupki.mos.ru/oldapi/api/Cssp/Article/GetEntity?id=171501",
    "https://zakupki.mos.ru/oldapi/api/Cssp/Article/GetEntity?id=213899",
    "https://old.zakupki.mos.ru/api/Cssp/Article/GetEntity?id=171501",
    "https://old.zakupki.mos.ru/api/Cssp/Article/GetEntity?id=213899",
    "https://zakupki.mos.ru/api/Cssp/Article/GetEntityCount?id=171501",
    "https://zakupki.mos.ru/api/Cssp/Article/GetEntityCount?id=213899",
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept": "application/json",
}

with httpx.Client(headers=headers, timeout=10.0, verify=False) as client:
    for url in tests:
        try:
            r = client.get(url)
            print(f"{url} -> {r.status_code}")
            if r.status_code == 200:
                print("   Body:", r.text[:250])
        except Exception as e:
            print(f"{url} -> Error: {e}")
