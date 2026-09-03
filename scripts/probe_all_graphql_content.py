import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
import json

GRAPHQL_URL = "https://zakupki.mos.ru/cms/api/graphql"
headers = {"Content-Type": "application/json"}

types_to_check = [
    ("contentPage", "{ contentItemId displayText content { html } }"),
    ("supplierInstructionStep", "{ contentItemId displayText content { html } }"),
    ("customerInstructionStep", "{ contentItemId displayText content { html } }"),
    ("regulationsPage", "{ contentItemId displayText content { html } }"),
    ("bankGuaranteeUserSteps", "{ contentItemId displayText content { html } }"),
    ("publicApiAccessSteps", "{ contentItemId displayText content { html } }"),
    ("stepsWithImages", "{ contentItemId displayText content { html } }"),
]

print("Probing GraphQL types...")
with httpx.Client(headers=headers, timeout=30.0, verify=False) as client:
    for type_name, fields in types_to_check:
        query = f"{{ {type_name}(first: 1000) {fields} }}"
        try:
            r = client.post(GRAPHQL_URL, json={"query": query})
            data = r.json()
            if "data" in data and data["data"].get(type_name) is not None:
                items = data["data"][type_name]
                print(f"[OK] {type_name}: {len(items)} items")
                if items:
                    sample = items[0]
                    html_len = len(sample.get("content", {}).get("html", "") or "")
                    print(f"     Sample: '{sample.get('displayText')}' (HTML len: {html_len})")
            else:
                print(f"[FAIL] {type_name}: {data.get('errors')}")
        except Exception as e:
            print(f"[ERROR] {type_name}: {e}")
