import httpx
import json

base_old = "https://old.zakupki.mos.ru/api/Cssp/Article"
tests = [
    f"{base_old}/Get?id=235739",
    f"{base_old}/Get?id=305516",
    f"{base_old}/Get?id=171501",
    f"{base_old}/Get?id=508580",
    f"{base_old}/Detail?id=235739",
    f"{base_old}/Details?id=235739",
    f"{base_old}/Query",
    f"{base_old}/LightQuery",
]

headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}

with httpx.Client(headers=headers, timeout=10.0, verify=False) as client:
    for url in tests:
        try:
            if "Query" in url:
                r = client.post(url, json={"filter": {}})
            else:
                r = client.get(url)
            print(f"{url} -> {r.status_code}")
            if r.status_code == 200:
                print("   Snippet:", r.text[:250])
        except Exception as e:
            print(f"{url} -> Error: {e}")
