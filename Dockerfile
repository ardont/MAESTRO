FROM dockerhub.timeweb.cloud/library/python:3.14-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Ставим PyTorch базовый (CPU версия, отлично работает на Mac)
RUN pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cpu

# Ставим остальные зависимости проекта
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .