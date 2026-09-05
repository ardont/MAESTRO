FROM dockerhub.timeweb.cloud/library/python:3.10-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим PyTorch с поддержкой CUDA (чтобы эмбеддер летал на видеокарте)
RUN pip3 install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121

# Ставим остальные зависимости проекта
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Копируем код
COPY . .
