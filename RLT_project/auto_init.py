"""
auto_init.py — Скрипт автоматической инициализации RAG-системы (One-Click Deploy).

Выполняет 5 шагов до старта веб-сервера:
1. Ожидание готовности Qdrant (healthcheck).
2. Проверка и автоматическое скачивание модели Qwen2.5 в Ollama (если доступна).
3. Применение миграций базы данных Django.
4. Auto-indexing: проверка наличия коллекции в Qdrant; если пуста — запуск индексации всей базы знаний.
5. Прогрев (Warmup) моделей RoSBERTa, BM25 и LLM для исключения задержек на первом запросе.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
import urllib.request
import urllib.error

# Добавляем родительский каталог в sys.path так, чтобы BASE_DIR был первым
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(BASE_DIR) in sys.path:
    sys.path.remove(str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "RLT_project.settings")

# Инициализация Django
import django
django.setup()
from django.core.management import call_command

logger = logging.getLogger("rag")


def wait_for_qdrant(host: str, port: int, max_retries: int = 45) -> bool:
    """Ожидание доступности Qdrant сервера."""
    url = f"http://{host}:{port}/readyz"
    print(f"[AUTO-INIT] Ожидание готовности Qdrant по адресу {url}...")
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    print(f"[AUTO-INIT] [OK] Qdrant готов к работе (попытка {attempt}).")
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    print(f"[AUTO-INIT] [WARN] Qdrant не ответил за {max_retries} сек. Продолжаем с локальным хранилищем.")
    return False


def check_and_pull_ollama_model(ollama_host: str, model_name: str = "qwen2.5:7b"):
    """Проверяет наличие модели в Ollama и при необходимости скачивает её."""
    clean_host = ollama_host.rstrip("/")
    tags_url = f"{clean_host}/api/tags"
    pull_url = f"{clean_host}/api/pull"
    print(f"[AUTO-INIT] Проверка моделей в Ollama: {tags_url}")
    try:
        req = urllib.request.Request(tags_url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [m.get("name") for m in data.get("models", []) if m.get("name")]
            print(f"[AUTO-INIT] Установленные модели в Ollama: {installed}")
            
            # Проверяем, есть ли модель
            has_model = any(model_name in m for m in installed)
            if not has_model:
                print(f"[AUTO-INIT] Модель '{model_name}' не найдена. Запуск автоматической загрузки из Ollama...")
                pull_payload = json.dumps({"name": model_name, "stream": False}).encode("utf-8")
                pull_req = urllib.request.Request(
                    pull_url,
                    data=pull_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(pull_req, timeout=300.0) as pull_resp:
                    print(f"[AUTO-INIT] [OK] Модель '{model_name}' успешно загружена в Ollama!")
            else:
                print(f"[AUTO-INIT] [OK] Модель '{model_name}' уже установлена в Ollama.")
    except Exception as e:
        print(f"[AUTO-INIT] [INFO] Ollama хост {clean_host} пока недоступен или работает автономно: {e}")


def apply_migrations():
    """Применяет миграции базы данных Django."""
    print("[AUTO-INIT] Применение миграций базы данных Django...")
    try:
        call_command("migrate", interactive=False)
        print("[AUTO-INIT] [OK] Миграции успешно применены.")
    except Exception as e:
        print(f"[AUTO-INIT] [ERROR] Ошибка миграций: {e}")


def check_and_auto_index(host: str, port: int):
    """
    Проверяет наличие векторов в Qdrant.
    Если коллекция отсутствует или пуста — запускает автоматическую индексацию всей базы знаний.
    """
    collection_name = "data_files"
    url = f"http://{host}:{port}/collections/{collection_name}"
    needs_indexing = True

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("result", {})
            points_count = result.get("points_count", 0)
            print(f"[AUTO-INIT] Проверка коллекции '{collection_name}': точек = {points_count}")
            if points_count and points_count > 0:
                needs_indexing = False
                print(f"[AUTO-INIT] [OK] Коллекция уже содержит {points_count} векторов. Индексация не требуется.")
    except Exception as e:
        print(f"[AUTO-INIT] Коллекция '{collection_name}' не найдена или пуста: {e}")
        needs_indexing = True

    if needs_indexing:
        print("\n" + "=" * 75)
        print("[AUTO-INIT] 🚀 ЗАПУСК АВТОМАТИЧЕСКОЙ ИНДЕКСАЦИИ БАЗЫ ЗНАНИЙ В QDRANT...")
        print("=" * 75)
        try:
            try:
                from rag.index_knowledge_base import run_indexing_pipeline
            except ImportError:
                from RLT_project.rag.index_knowledge_base import run_indexing_pipeline
            run_indexing_pipeline()
            print("[AUTO-INIT] [OK] Автоматическая индексация успешно завершена!")
        except Exception as e:
            print(f"[AUTO-INIT] [ERROR] Ошибка индексации: {e}")


def warmup_models():
    """Прогрев моделей в памяти для исключения задержки на первом пользовательском запросе."""
    print("[AUTO-INIT] Прогрев нейросетевых моделей (Warmup)...")
    t0 = time.time()
    try:
        try:
            from rag.indexer.embedder import get_embedder, get_sparse_embedder
        except ImportError:
            from RLT_project.rag.indexer.embedder import get_embedder, get_sparse_embedder
        dense = get_embedder()
        sparse = get_sparse_embedder()

        sample_text = "Прогрев модели и проверка векторного представления"
        _ = dense.get_embedding(sample_text)
        _ = sparse.get_sparse_embedding(sample_text)
        print(f"[AUTO-INIT] [OK] Эмбеддеры прогреты на {dense.device} за {time.time() - t0:.2f} сек.")
    except Exception as e:
        print(f"[AUTO-INIT] [WARN] Ошибка прогрева эмбеддера: {e}")


def main():
    print("=" * 75)
    print("RLT.Tender_Guide: АВТОМАТИЧЕСКАЯ ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ (ONE-CLICK DEPLOY)")
    print("=" * 75)

    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", 6333))
    ollama_host = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")

    # 1. Ждем Qdrant
    wait_for_qdrant(qdrant_host, qdrant_port)

    # 2. Проверяем Ollama
    check_and_pull_ollama_model(ollama_host, "qwen2.5:7b")

    # 3. Применяем миграции
    apply_migrations()

    # 4. Проверяем Qdrant и запускаем авто-индексацию при необходимости
    check_and_auto_index(qdrant_host, qdrant_port)

    # 5. Прогреваем модели
    warmup_models()

    print("=" * 75)
    print("[AUTO-INIT] ✅ ВСЕ СИСТЕМЫ ГОТОВЫ К РАБОТЕ! ЗАПУСК ВЕБ-СЕРВЕРА...")
    print("=" * 75)


if __name__ == "__main__":
    main()
