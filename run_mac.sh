#!/usr/bin/env bash
# ==============================================================================
# run_mac.sh — Безопасный скрипт запуска RLT Support Agent System на macOS (MacBook)
# Поддерживает Apple Silicon (M1/M2/M3/M4) и Intel Mac.
# Интеграция: База знаний MAESTRO / Qdrant, Ollama (LLM) и Django/FastStream API.
# ==============================================================================

set -e

# Цвета для вывода в терминале
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================================${NC}"
echo -e "${GREEN}   RLT Support Agent System — Запуск на macOS (MacBook)   ${NC}"
echo -e "${BLUE}================================================================${NC}"

# Определение рабочей директории проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARCH=$(uname -m)
echo -e "Архитектура процессора: ${YELLOW}$ARCH${NC} ($(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon / Intel'))"

# 1. Проверка версии Python
PYTHON_BIN=""
for cmd in python3.11 python3.12 python3; do
    if command -v "$cmd" &> /dev/null; then
        VER=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        MAJOR=$($cmd -c 'import sys; print(sys.version_info.major)')
        MINOR=$($cmd -c 'import sys; print(sys.version_info.minor)')
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[ОШИБКА] Не найден Python >= 3.10. Установите Python через brew:${NC}"
    echo "  brew install python@3.11"
    exit 1
fi
echo -e "Используется Python: ${GREEN}$PYTHON_BIN ($($PYTHON_BIN --version))${NC}"

# 2. Настройка виртуального окружения (.venv)
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[INFO] Виртуальное окружение не найдено. Создаем .venv...${NC}"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo -e "Виртуальное окружение: ${GREEN}активировано ($VENV_DIR)${NC}"

# 3. Проверка и установка зависимостей
if ! python -c "import django, qdrant_client" &> /dev/null; then
    echo -e "${YELLOW}[INFO] Установка зависимостей из requirements_mac.txt...${NC}"
    pip install --upgrade pip
    if [ -f "$SCRIPT_DIR/requirements_mac.txt" ]; then
        pip install -r "$SCRIPT_DIR/requirements_mac.txt"
    else
        pip install -r "$SCRIPT_DIR/requirements.txt"
    fi
else
    echo -e "Базовые библиотеки: ${GREEN}установлены${NC}"
fi

# 4. Настройка путей PYTHONPATH и переменных окружения
export PYTHONPATH="$SCRIPT_DIR/RLT_project:$SCRIPT_DIR:$PYTHONPATH"
export DJANGO_SETTINGS_MODULE="RLT_project.settings"

# По умолчанию подключаемся к локальному серверу Qdrant
export QDRANT_HOST="${QDRANT_HOST:-localhost}"
export QDRANT_PORT="${QDRANT_PORT:-6333}"
export QDRANT_COLLECTION="${QDRANT_COLLECTION:-data_files}"
export QDRANT_MODE="${QDRANT_MODE:-server}"

# Путь к локальному хранилищу Maestro Qdrant при запуске контейнера
MAESTRO_QDRANT_STORAGE="$SCRIPT_DIR/qdrant_storage"
if [ -d "$HOME/Desktop/python_projects/MAESTRO/qdrant_storage" ]; then
    MAESTRO_QDRANT_STORAGE="$HOME/Desktop/python_projects/MAESTRO/qdrant_storage"
fi

# Настройки Ollama
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gpt-oss:20b}"

# 5. Проверка доступности сервисов (Qdrant & Ollama)
echo -e "\n${BLUE}--- Проверка подключений к сервисам ---${NC}"

# Проверка Qdrant
if curl -s "http://$QDRANT_HOST:$QDRANT_PORT/readyz" &> /dev/null || curl -s "http://$QDRANT_HOST:$QDRANT_PORT/collections" &> /dev/null; then
    echo -e "Векторная БД Qdrant ($QDRANT_HOST:$QDRANT_PORT): ${GREEN}ПОДКЛЮЧЕНО (Коллекция: $QDRANT_COLLECTION)${NC}"
else
    echo -e "Векторная БД Qdrant: ${YELLOW}Сервер $QDRANT_HOST:$QDRANT_PORT не отвечает.${NC}"
    echo -e "  Для запуска Qdrant с базой данных MAESTRO выполните в отдельном терминале:"
    echo -e "  ${GREEN}docker run -d -p 6333:6333 -v \"$MAESTRO_QDRANT_STORAGE:/qdrant/storage\" qdrant/qdrant:v1.19.0${NC}"
fi

# Проверка Ollama
if curl -s "$OLLAMA_HOST/api/tags" &> /dev/null; then
    echo -e "LLM сервер Ollama ($OLLAMA_HOST): ${GREEN}ПОДКЛЮЧЕНО (Модель: $OLLAMA_MODEL)${NC}"
else
    echo -e "LLM сервер Ollama: ${YELLOW}$OLLAMA_HOST не запущен. Для локальной генерации запустите приложение Ollama.${NC}"
fi

# 6. Меню режимов запуска
MODE="${1:-server}"

case "$MODE" in
    server|web)
        echo -e "\n${GREEN}=== Запуск Django API сервера (0.0.0.0:8000) ===${NC}"
        python "$SCRIPT_DIR/RLT_project/manage.py migrate" --noinput
        python "$SCRIPT_DIR/RLT_project/manage.py runserver" 0.0.0.0:8000
        ;;

    test)
        echo -e "\n${GREEN}=== Запуск набора тестов ===${NC}"
        python -m unittest tests.test_stream_workflow
        ;;

    qa)
        echo -e "\n${GREEN}=== Запуск комплексного QA тест-сьюта ===${NC}"
        python "$SCRIPT_DIR/qa_test_suite.py" --url "http://localhost:8000/api/ask/"
        ;;

    kafka)
        echo -e "\n${GREEN}=== Запуск Kafka подписчика FastStream ===${NC}"
        python -m chat.kafka.subscribers
        ;;

    docker)
        echo -e "\n${GREEN}=== Запуск полного стека через Docker Compose ===${NC}"
        docker compose up --build
        ;;

    check)
        echo -e "\n${GREEN}=== Проверка окружения выполнена успешно ===${NC}"
        ;;

    *)
        echo -e "${YELLOW}Использование:${NC} ./run_mac.sh [server|test|qa|kafka|docker|check]"
        echo "  server — запуск Django веб-сервера (по умолчанию)"
        echo "  test   — запуск unit-тестов"
        echo "  qa     — запуск комплексного тестирования RAG"
        echo "  kafka  — запуск обработчика очередей Kafka"
        echo "  docker — запуск в изолированном Docker-окружении"
        ;;
esac
