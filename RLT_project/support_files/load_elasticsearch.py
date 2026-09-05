
discovery_type = "single-node"  # один узел не для прода

from elasticsearch import Elasticsearch
import pandas as pd
from elasticsearch.helpers import bulk
from text_pipeline import build_semantic_text

es = Elasticsearch("http://localhost:9200")

INDEX_NAME = "products_v6"

mapping = {
    "settings": {
        "analysis": {
            "analyzer": {
                "ru_analyzer": {
                    "type": "standard",
                    "stopwords": "_russian_"
                }
            }
        }
    },
    "mappings": {
        "dynamic": True,
        "properties": {
            "id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "ru_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "category": {
                "type": "text",
                "analyzer": "ru_analyzer"
            },
            "semantic_text": {
                "type": "text",
                "analyzer": "ru_analyzer"
            },
            "attributes": {
                "type": "flattened"
            }
        }
    }
}

# пересоздание индекса
if es.indices.exists(index=INDEX_NAME):
    es.indices.delete(index=INDEX_NAME)

es.indices.create(index=INDEX_NAME, body=mapping)

print("Index created")

es.indices.put_alias(index=INDEX_NAME, name="products")

df = pd.read_csv(
    "cte.csv",
    sep=";",
    encoding="utf-8",
    header=None,
    names=['id', 'name', 'category', 'character']
)


def generate_actions(dfjktg):
    for i, row in enumerate(dfjktg.itertuples(index=False), 1):
        if i % 10000 == 0:
            print(f"Processed: {i}")

        row_dict = row._asdict()

        text, attrs = build_semantic_text(row_dict)

        if not text:
            continue

        # attrs приходит из build_semantic_text
        clean_attrs = {}
        for k, v in attrs.items():
            if k == "character_raw":
                continue
            clean_attrs[k] = str(v)

        # обрезаем character_raw до безопасного размера (например, 1000 символов)
        character_raw_safe = (attrs.get("character_raw") or "")[:1000]

        yield {
            "_index": INDEX_NAME,
            "_id": str(row_dict["id"]),
            "_source": {
                "id": str(row_dict["id"]),
                "name": attrs.get("name"),
                "category": attrs.get("category") or "",
                "semantic_text": text,
                "attributes": clean_attrs,
                "character_raw": character_raw_safe,
                "_raw_row": row_dict
            }
        }


from elasticsearch.helpers import bulk
import json

success, failed = bulk(
    es.options(request_timeout=60),
    generate_actions(df),
    chunk_size=500,
    raise_on_error=False,
    raise_on_exception=False
)

print(f"SUCCESS: {success}")
print(f"FAILED: {len(failed) if failed else 0}")

if failed:
    print("\n===== ERRORS SAMPLE =====\n")

    for i, err in enumerate(failed[:10]):  # первые 10
        action = err.get("index") or err.get("create")

        error_reason = action.get("error", {})
        doc_id = action.get("_id")

        print(f"\n--- ERROR #{i+1} ---")
        print("ID:", doc_id)
        print("ERROR:", json.dumps(error_reason, ensure_ascii=False, indent=2))

        source = action.get("data", {})
        raw_row = source.get("_raw_row")

        print("RAW ROW:", raw_row)


print(f"Loaded: {success}, Failed: {len(failed) if failed else 0}")


