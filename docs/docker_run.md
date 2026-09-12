# Запуск RAG-микросервиса

Основная конфигурация — `Dockerfile` и `docker-compose.yml`.
`Dockerfile_ser` совпадает с основным Dockerfile; `docker-compose_ser.yml`
подключает основной Compose (нужен Docker Compose >= 2.20).
Python в образе — 3.12, Debian Bookworm, CPU-инференс эмбеддингов.
Ollama работает отдельно и может использовать GPU на своей машине.

```sh
docker compose config --quiet
docker compose up -d --build
docker compose logs -f rag
```

Сервис `rag` запускает `faststream run chat.kafka.broker:app --workers 1`.
Django, миграции и порт 8001 для этого запуска не используются. Один worker
предотвращает загрузку пяти копий модели эмбеддингов в память.
Kafka, Redis и Qdrant поднимаются в том же Compose. Данные и кэш моделей
сохраняются в именованных томах. Код берётся из образа: после изменений нужна
повторная сборка. Запуск не удаляет и не переиндексирует коллекции Qdrant.
Новая пустая коллекция сама не наполняется — импорт базы знаний выполняется отдельно.

Настройки перечислены в `.env.template`. Существующий `.env` не перезаписывайте:
согласуйте `LLM_REQUEST_TOPIC` и `LLM_RESPONSE_TOPIC` с основным приложением.
Для контейнера Kafka доступна как `kafka:29092`, для программ на хосте —
`localhost:9092`. `KAFKA_URL` из старого `.env` намеренно не используется
контейнером: его `localhost` означал бы сам RAG-контейнер.
Для внешнего брокера задайте `RAG_KAFKA_URL` и обеспечьте доступность всех
адресов, возвращаемых его advertised listeners. Встроенная Kafka при этом
продолжит запускаться; для полностью внешней инфраструктуры используйте
отдельный Compose override без локальной Kafka и зависимости от неё.

`OLLAMA_HOST` по умолчанию равен `http://host.docker.internal:11434`.
Ollama должна слушать интерфейс, доступный контейнеру, и содержать модель
`OLLAMA_MODEL` (по умолчанию `gpt-oss:20b`).

RoSBERTa подключается из `EMBEDDING_MODEL_HOST_PATH` (по умолчанию
`/Users/todaisy/models/ru-en-RoSBERTa`) в `/models/ru-en-RoSBERTa` только для
чтения. На другом компьютере задайте свой путь в `.env`. Compose передаёт
этот контейнерный путь через `EMBEDDING_MODEL_NAME`. Токенизатор и dense-модель
загружаются с `local_files_only=True`, без обращения к Hugging Face.
Отсутствующая папка вызывает ошибку, а не автоматическое скачивание.
Это настройка RoSBERTa; отдельный sparse-эмбеддер BM25 имеет свой загрузчик.

## Зависимости и диагностика pip

`requirements.txt` сохранён в UTF-8 и содержит прямые зависимости.
Транзитивные версии, включая yarl, подбирает pip для целевого Python/Linux.
Это не полный lockfile. `pip check` выполняется при сборке.
CPU-версия torch устанавливается отдельно из официального PyTorch index;
повторная установка из requirements сохраняет удовлетворяющую версию.
FastStream установлен с extras `kafka,cli`, необходимыми для запуска worker.

`yarl==1.24.5` есть в публичном PyPI, включая wheel для CPython 3.12/Linux.
Исходный список зависимостей разрешился при проверке через публичный PyPI.
Поэтому фрагмент `from versions: none` сам по себе не доказывает конфликт
версий: проверьте предшествующие сообщения pip о сети, TLS и зеркале индекса.
Сборка явно использует `https://pypi.org/simple`. Для корпоративного зеркала
задайте `BUILD_PIP_INDEX_URL`, для PyTorch — `TORCH_INDEX_URL`.
Не передавайте пароли в build args.

Исходный `_ser` конфиг дополнительно требовал NVIDIA runtime для самого RAG,
хотя GPU нужен отдельному Ollama, и запускал тот же Django. Эти требования сняты.
В старом `_ser` Compose `build: .` вообще выбирал `Dockerfile`, а не `Dockerfile_ser`.

```sh
docker compose run --rm --no-deps rag python -m pip check
docker compose run --rm --no-deps rag python -m unittest discover -s tests -v
```

Источники: [FastStream CLI](https://faststream.ag2.ai/latest/getting-started/cli/),
[Kafka Docker quickstart](https://kafka.apache.org/39/getting-started/quickstart/),
[yarl в PyPI](https://pypi.org/project/yarl/).
