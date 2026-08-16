#!/bin/bash
# ==============================================================================
# Скрипт автоматического запуска RLT.Tender_Guide на macOS (MacBook Pro / Air)
# ==============================================================================

# Останавливать выполнение при критических ошибках
set -e

# Переход в директорию скрипта
cd "$(dirname "$0")"

echo "======================================================"
echo "🚀 Запуск RLT.Tender_Guide на macOS"
echo "======================================================"

# 1. Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Ошибка: python3 не найден. Установите Python через brew install python"
    exit 1
fi

# 2. Создание и активация виртуального окружения
if [ ! -d ".venv" ]; then
    echo "📦 Создание виртуального окружения .venv..."
    python3 -m venv .venv
fi

echo "🔄 Активация виртуального окружения..."
source .venv/bin/activate

# 3. Установка совместимых с macOS зависимостей
echo "📥 Проверка и установка зависимостей (macOS)..."
pip install --upgrade pip
pip install -r requirements_mac.txt

# 4. Проверка работы Ollama
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "✅ Ollama запущена и доступна!"
else
    echo "⚠️  Внимание: Ollama не запущена на http://localhost:11434."
    echo "   Запустите приложение Ollama на Mac, если требуется генерация ответов через LLM."
fi

# 5. Переход в Django проект и миграции
cd RLT_project

echo "🗄️ Применение миграций базы данных..."
python manage.py migrate

# 6. Запуск сервера
echo "======================================================"
echo "🌐 Сервер запускается по адресу: http://127.0.0.1:8000"
echo "======================================================"
python manage.py runserver 0.0.0.0:8000
