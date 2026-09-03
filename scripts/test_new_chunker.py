import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
from pathlib import Path

# Добавляем корень проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from RLT_project.rag.indexer.chunker import process_document_to_chunks

kb_clean_file = BASE_DIR / "dataset" / "kb_clean.json"
with open(kb_clean_file, "r", encoding="utf-8") as f:
    docs = json.load(f)

print(f"Всего документов в kb_clean.json: {len(docs)}")

all_chunks = []
table_chunks = []
step_chunks = []
image_chunks = []

for d in docs:
    chunks = process_document_to_chunks(d)
    for ch in chunks:
        all_chunks.append(ch)
        if "|" in ch["text"] and "---" in ch["text"]:
            table_chunks.append(ch)
        if ch.get("step_number"):
            step_chunks.append(ch)
        if ch.get("images"):
            image_chunks.append(ch)

print(f"Всего сгенерировано чанков: {len(all_chunks)}")
print(f"Чанков с таблицами: {len(table_chunks)}")
print(f"Чанков с шагами инструкций: {len(step_chunks)}")
print(f"Чанков с привязанными скриншотами: {len(image_chunks)}")

# Проверяем структуру одного чанка с шагом и картинкой
if step_chunks:
    sample_step = step_chunks[0]
    print("\n--- ОБРАЗЕЦ ЧАНКА С ШАГОМ ИНСТРУКЦИИ ---")
    print(f"ID: {sample_step['chunk_id']}")
    print(f"Заголовок документа: {sample_step['title']}")
    print(f"Раздел (breadcrumbs): {sample_step['section_header']}")
    print(f"Номер шага: {sample_step['step_number']}")
    print(f"Категория: {sample_step['category']}")
    print(f"Картинки: {sample_step['images']}")
    print(f"Текст чанка (первые 250 символов):\n{sample_step['text'][:250]}...")

if table_chunks:
    sample_tbl = table_chunks[0]
    print("\n--- ОБРАЗЕЦ ЧАНКА С ТАБЛИЦЕЙ ---")
    print(f"Заголовок: {sample_tbl['title']}")
    print(f"Раздел: {sample_tbl['section_header']}")
    print(f"Текст таблицы:\n{sample_tbl['text'][:350]}...")
