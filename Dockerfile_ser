# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/RLT_project \
    HF_HOME=/root/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/root/.cache/fastembed

# OpenMP is needed by native CPU inference libraries.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --index-url "$PIP_INDEX_URL" --upgrade pip \
    && python -m pip install --index-url "$TORCH_INDEX_URL" 'torch==2.14.0' \
    && python -m pip install --index-url "$PIP_INDEX_URL" -r requirements.txt \
    && python -m pip check

COPY . .
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["faststream", "run", "chat.kafka.broker:app", "--workers", "1"]
