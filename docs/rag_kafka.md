# RAG → Kafka

`new_message_handler` передаёт `NewMessageEvent.data.text` в асинхронный
генератор `rag_pipeline(user_message, chat=None, category_filter=None)`.
`user_uuid` и `chat_id` остаются в Kafka-обработчике для адресации ответа.
Django и объект Chat для Kafka не требуются. Входной контракт сейчас не содержит
историю диалога, context_cache или category_filter: эти данные из другого
микросервиса автоматически не загружаются.

Полный синхронный алгоритм `rag_pipeline_result` выполняется через
`asyncio.to_thread`: поиск, GraphRAG, Redis, Ollama, fallback и обработка ссылок
не блокируют цикл событий Kafka. Для устаревшего Django endpoint сохранён
синхронный вызов `rag_pipeline_result`.

| Событие пайплайна | Публикации Kafka |
| --- | --- |
| `token` | `NEW_TOKEN`, текст в `data.token`, последовательный `data.id` с нуля |
| `done` | `END_GENERATION`, полный текст в `data.all_text` |
| `block` | `NEW_TOKEN` с текстом отказа, затем `END_GENERATION` с `meta.need_to_block_chat=true` |
| `off-topic` | `NEW_TOKEN` с текстом отказа, затем `END_GENERATION` с `meta.off_topic_message=true` |
| `error` | `NEW_TOKEN` с сообщением об ошибке, затем `END_GENERATION` с `meta.error=true` |

`block`, `off-topic`, `error` терминальные: дополнительного `done` нет.
Kafka key — `chat_id`; заголовок `event_name` совпадает с типом Kafka-события.
Текущий RAG отправляет весь обработанный ответ одним `token`, затем `done`.
Это не поток сырых токенов Ollama: сначала должны завершиться fallback и
санитария ссылок. Источники включены в текст; отдельные поля citations/images
не добавляются к существующему Kafka-контракту.

Проверка мата использует существующий `router.check_guardrails` перед LLM,
кэшем и поиском. Затем отдельный промпт классификатора Ollama проверяет тему.
Только точный ответ `OFF_TOPIC` означает отказ; сомнения, короткие уточнения,
недоступность модели и некорректный ответ классификатора пропускают запрос
в обычный RAG. Отсутствие документов не означает `off-topic`.
Классификация добавляет один запрос к Ollama, в том числе перед чтением кэша.
Ключ кэша учитывает категорию; ответы с объектом Chat не кэшируются глобально.

Проверки без внешних сервисов:

```sh
PYTHONPATH=RLT_project .venv/bin/python -m unittest discover -s tests -v
```

Для проверки в окружении сервисов требуются `LLM_REQUEST_TOPIC`,
`LLM_RESPONSE_TOPIC`, `KAFKA_URL`, `OLLAMA_HOST` и настроенный поиск.
Redis необязателен: при отсутствии клиента/сервера выполняется обычный RAG.
