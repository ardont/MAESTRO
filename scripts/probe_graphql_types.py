import httpx
import json

url = "https://zakupki.mos.ru/cms/api/graphql"
query_schema = "{ __schema { queryType { fields { name args { name } } } } }"
r = httpx.post(url, json={"query": query_schema}, headers={"content-type": "application/json"}, timeout=15)
fields = r.json()["data"]["__schema"]["queryType"]["fields"]
print(f"Total query fields: {len(fields)}")

forbidden = {"careInfoService", "consultingMethodologicalSupport", "coopStatistics", "factoringLanding", "menu", "taxonomy"}

results = {}
for f in fields:
    name = f["name"]
    args = [a["name"] for a in f["args"]]
    if "first" in args and name not in forbidden:
        q = f"{{ {name}(first: 5) {{ __typename }} }}"
        try:
            res = httpx.post(url, json={"query": q}, headers={"content-type": "application/json"}, timeout=5)
            data = res.json()
            if "data" in data and data["data"].get(name):
                cnt = len(data["data"][name])
                results[name] = cnt
                print(f"FOUND: {name} -> has {cnt}+ items")
        except Exception as e:
            pass

print("\nAll accessible types with items:")
for k, v in results.items():
    print(f" - {k}: {v}")
