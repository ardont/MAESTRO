import json
import asyncio
from typing import Literal, AsyncGenerator
from abc import ABC

import aiohttp
from pydantic import BaseModel

import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")

IS_TESTING = False

from .events import (
    LLMBaseEvent, LLMTokenEvent, LLMDoneEvent, LLMErrorEvent,
    LLMBlockEvent, LLMOffTopicEvent, LLM_TOKEN_EVENT, LLM_DONE_EVENT,
    LLM_ERROR_EVENT, LLM_BLOCK_EVENT, LLM_OFF_TOPIC_EVENT, REDIRECTED_TO_OPERATOR,
)

async def stream_local_llm_response(prompt: str, model_name: str = "gpt-oss:20b") -> AsyncGenerator[LLMBaseEvent, None]:
    """
    Потоковый вызов локальной LLM через Ollama.
    Отдает токены через yield по мере генерации, а в конце — событие о завершении.
    """
    if IS_TESTING:
        res = f"Это ответ для теста - работает ли передача токенов по кафке на промпт {prompt}"
        for token in res:
            yield LLMTokenEvent(data=token)
            await asyncio.sleep(0.05)
        yield LLMDoneEvent()
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.9
                    }
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status == 200:
                    # Читаем поток построчно
                    async for line in resp.content:
                        if line:
                            # line — это bytes, нужно декодировать
                            decoded = line.decode('utf-8').strip()
                            if not decoded:
                                continue
                            try:
                                data = json.loads(decoded)
                            except json.JSONDecodeError:
                                continue
                            token = data.get("response", "")
                            if token:
                                yield LLMTokenEvent(data=token)
                else:
                    # Обработка ошибки HTTP
                    print(data=f"HTTP {resp.status}: {await resp.text()}")
                    yield LLMErrorEvent(data=f"HTTP {resp.status}: {await resp.text()}")
                    return
    except Exception as e:
        print(e)
        yield LLMErrorEvent(data=str(e))
        return

    # Сигнал о завершении
    yield LLMDoneEvent()