"""
Модуль: chunking.py

Назначение:
  Унифицированный фасад для разбиения базы знаний на чанки (JSON Lines экспорт).
  Интегрирован с основным модулем умного иерархического чанкинга (RLT_project/rag/indexer/chunker.py).

Какую проблему решает:
  Обеспечивает обратную совместимость для скриптов и тестов, ожидающих генерацию
  файла `chunks.jsonl`, транслируя вызовы в современный семантический чанкер
  с сохранением контекста заголовков, таблиц и скриншотов.
"""

import json
import os
from pathlib import Path
from typing import Tuple, List, Dict, Any

from .indexer.chunker import process_document_to_chunks

DATA_DIR = Path(__file__).resolve().parent / "data"
IN_FILE = Path(__file__).resolve().parent.parent.parent / "dataset" / "kb_clean.json"
OUT_FILE = DATA_DIR / "chunks.jsonl"


def build_all_chunks(input_file: Path = IN_FILE, output_file: Path = OUT_FILE) -> Tuple[int, Path]:
    """
    Выполняет полный проход по очищенному датасету и сохраняет результат в JSON Lines.
    
    Возвращает:
      (количество_чанков, путь_к_файлу)
    """
    os.makedirs(output_file.parent, exist_ok=True)

    if not input_file.exists():
        print(f"[ОШИБКА] Входной файл не найден: {input_file}")
        return 0, output_file

    with open(input_file, "r", encoding="utf-8") as f:
        articles = json.load(f)

    all_chunks: List[Dict[str, Any]] = []

    for article in articles:
        text = article.get("text", "").strip()
        if not text:
            continue

        doc_chunks = process_document_to_chunks(article)
        all_chunks.extend(doc_chunks)

    with open(output_file, "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    print(f"[OK] Сгенерировано {len(all_chunks)} чанков в {output_file}")
    return len(all_chunks), output_file


if __name__ == "__main__":
    count, path = build_all_chunks()
    print(f"Готово: {count} чанков записано в {path}")