"""
Скрипт: sync_github_skills.py

Назначение:
  Автоматическая загрузка, обновление и синхронизация специализированных скиллов (Agent Skills)
  из открытых репозиториев GitHub для проведения углубленного RAG-тестирования, проверки гипотез,
  мультимодального анализа скриншотов и аудита базы знаний.

Поддерживаемые источники скиллов:
  - anthropics/courses / skills
  - deepmind / agentic skills
  - кастомные репозитории навыков для RAG и LLM-бенчмарков
"""

import os
import sys
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# Список рекомендованных репозиториев навыков и инструментов для тестирования RAG
GITHUB_SKILLS_REPOS = [
    {
        "name": "rag-evaluation-skills",
        "url": "https://github.com/explodinggradients/ragas.git",
        "description": "Инструменты автоматической оценки метрик RAG (Faithfulness, Answer Relevance, Context Recall)"
    }
]


def sync_skills():
    print("=" * 75)
    print("СИНХРОНИЗАЦИЯ И ЗАГРУЗКА АГЕНТНЫХ СКИЛЛОВ С GITHUB")
    print("=" * 75)
    print(f"Целевая папка для скиллов: {SKILLS_DIR}\n")

    for repo in GITHUB_SKILLS_REPOS:
        target_path = SKILLS_DIR / repo["name"]
        print(f"[*] Скилл: {repo['name']} — {repo['description']}")
        if target_path.exists():
            print(f"    Репозиторий уже существует. Обновление (git pull)...")
            try:
                subprocess.run(["git", "-C", str(target_path), "pull"], check=True, capture_output=True, text=True)
                print(f"    [OK] Успешно обновлено.")
            except Exception as e:
                print(f"    [!] Предупреждение при обновлении: {e}")
        else:
            print(f"    Клонирование {repo['url']}...")
            try:
                subprocess.run(["git", "clone", "--depth", "1", repo["url"], str(target_path)], check=True, capture_output=True, text=True)
                print(f"    [OK] Успешно склонировано в {target_path.name}")
            except Exception as e:
                print(f"    [!] Ошибка клонирования (проверьте доступ к сети): {e}")

    print("\n" + "=" * 75)
    print("Готово. Навыки доступны в директории: skills/")
    print("=" * 75)


if __name__ == "__main__":
    sync_skills()
