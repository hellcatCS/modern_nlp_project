# Чат-бот ресторана

Ассистент для гостей: ответы по меню и документам (RAG), бронирование столов в PostgreSQL, эскалация к менеджеру. LLM вызывается через **LangChain** с **function calling**; конфигурация — **Pydantic Settings** и **Docker Compose**.

---

## 1. Функционал

| Область | Что делает бот |
|--------|----------------|
| **Диалог** | Отвечает от имени ресторана по системному промпту; история сообщений хранится в БД на пользователя. |
| **Инструменты (tools)** | Поиск фактов в базе знаний (Qdrant), бронирование и отмена столиков, запрос эскалации к живому менеджеру. |
| **RAG** | Документы (md, txt, json, pdf) режутся на чанки, эмбеддинги кладутся в **Qdrant**; при вопросе — поиск похожих фрагментов и передача в LLM. |
| **Бронирование** | Слот 2 часа, шаг времени 30 минут, проверка пересечений и вместимости стола; код брони — 7 символов (`booking_id`). |
| **CLI** | Команды загрузки документов, списков наборов, активации набора, переиндексации (см. ниже). |
| **Наблюдаемость** | Логи приложения (INFO+) в **Elasticsearch** / просмотр в **Kibana**; счётчики и гистограммы в **Prometheus**; дашборд в **Grafana**. |

---

## 2. Почему выбраны эти инструменты

| Компонент | Обоснование |
|-----------|-------------|
| **LangChain + `ChatOpenAI`** | Единый клиент для OpenAI, OpenRouter и **vLLM** (OpenAI-совместимый endpoint): меняется только `base_url` и имя модели. |
| **Function calling** | Явные сигнатуры инструментов (поиск в Qdrant, БД) вместо ненадёжного «голого» JSON от модели. |
| **Qdrant** | Локальный векторный поиск, HTTP API, удобно поднимать в Docker; альтернатива — тяжёлый полнотекстовый поиск в SQL для учебного объёма. |
| **PostgreSQL** | Надёжное хранение пользователей, диалогов, столов и броней с проверкой пересечений по времени. |
| **vLLM (опционально)** | Для сценария без облачного API: один GPU-сервер отдаёт модель по HTTP, как у OpenAI. |
| **Hugging Face эмбеддинги** | В режиме `USE_VLLM_LLM=true` чат не ходит в OpenAI — эмбеддинги для RAG тоже локальны; при блокировке региона OpenAI можно перейти на HF без смены кода бота. |
| **Elasticsearch + Kibana** | Полнотекстовый поиск и фильтрация по логам при отладке и демонстрации работы сервиса. |
| **Prometheus + Grafana** | Стандарт для метрик; Prometheus снимает `/metrics` с процесса бота, Grafana визуализирует готовый дашборд. |
| **`network_mode: host` для `app`** | На Linux выравнивает сетевой стек с хостом (доступ к `api.openai.com` / локальному vLLM на `127.0.0.1` так же, как у процессов вне Docker). БД и Qdrant доступны по `127.0.0.1` и проброшенным портам. |

---

## 3. Быстрый старт (рабочий пример)

**Требования:** Linux с Docker, Docker Compose v2. Для чата с **OpenAI** — ключ в `.env`. Для **локального vLLM** — отдельно запущенный сервер с GPU (см. п. 5).

```bash
cd modern_nlp_project
cp .env.example .env
# Отредактируйте .env: OPENAI_API_KEY или USE_VLLM_LLM=true и параметры vLLM

docker compose build app
docker compose up -d
docker compose --profile app run --rm app
```

- Первая команда собирает образ приложения (после изменений в `src/` пересобирайте снова).
- `docker compose up -d` поднимает **PostgreSQL**, **Qdrant**, **Elasticsearch**, **Kibana**, **Prometheus**, **Grafana**. Сервис **`app`** в профиле `app` при `up -d` **не** стартует — чтобы не занимать порт **9090** метрик параллельно с интерактивным `run`.
- Интерактивный бот: `docker compose --profile app run --rm app`.

Сброс данных БД и томов:

```bash
docker compose down -v
docker compose up -d
docker compose --profile app run --rm app
```

---

## 4. Как пользоваться

1. После запуска введите обычный текст — это сообщение гостя; бот ответит через LLM и при необходимости вызовет инструменты.
2. Команды начинаются с `/`:

| Команда | Описание |
|---------|----------|
| `/help` | Список команд |
| `/upload <путь> [имя_набора]` | Загрузить файл в набор знаний |
| `/list_docs` | Документы |
| `/list_sets` | Наборы знаний |
| `/activate_set <id>` | Сделать набор активным для RAG |
| `/reindex [id]` | Переиндексация набора |

3. Выход: `exit` или Ctrl+C.

---

## 5. Режимы LLM (OpenAI / vLLM)

**OpenAI (и опционально OpenRouter как fallback в коде):** в `.env` задайте `OPENAI_API_KEY`, `USE_VLLM_LLM` не указывайте или `false`.

**Локальный vLLM:** `USE_VLLM_LLM=true`, пустой `OPENAI_API_KEY`, `VLLM_BASE_URL` (например `http://127.0.0.1:8000/v1`), `VLLM_MODEL` = то же имя, что **`--served-model-name`** при запуске vLLM.

Бот использует **tools** (`tool_choice: auto`). Сервер vLLM нужно запускать с поддержкой автоматического выбора инструментов, иначе будет ошибка 400:

```text
"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser
```

Минимально (пример для Qwen-подобных моделей в духе документации vLLM):

```bash
vllm serve /path/to/Qwen3-30B-A3B \
  --served-model-name Qwen \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --host 0.0.0.0 --port 8000
```

Для **Qwen3** в документации vLLM часто указывают парсер **`qwen3_xml`**. В `.env` выставьте `VLLM_MODEL` в точности как зарегистрированное имя модели (`GET /v1/models`).

---

## 6. Наблюдаемость

Переменные по умолчанию (см. `.env.example`): `OBSERVABILITY_ENABLED=true`, `ELASTICSEARCH_ENABLED=true`, `PROMETHEUS_METRICS_ENABLED=true`.

| Сервис | URL на хосте с Docker | Комментарий |
|--------|-------------------------|-------------|
| Kibana | http://127.0.0.1:5601 | Data View: шаблон `restaurant-bot-logs-*`, поле времени `@timestamp`, в Discover расширьте интервал времени при необходимости |
| Grafana | http://127.0.0.1:3000 | Логин / пароль: **admin** / **admin** (из `docker-compose.yml`) |
| Prometheus UI | http://127.0.0.1:9091 | UI на **9091**; порт **9090** на хосте — эндпоинт **`/metrics` приложения**, не веб-интерфейс Prometheus |
| Elasticsearch | http://127.0.0.1:9200 | API; проверка индексов: `curl "http://127.0.0.1:9200/_cat/indices/restaurant-bot-logs-*?v"` |

Метрики в Prometheus появляются, когда **запущен** бот и цель **Status → Targets** для `restaurant_bot` в состоянии **UP** (нужен процесс с `PROMETHEUS_METRICS_ENABLED=true` на `127.0.0.1:9090`).

Если браузер открыт **не** на машине с Docker, `http://127.0.0.1:5601` указывает на локальный ПК — используйте SSH-туннель или IP сервера, например:

`ssh -L 5601:127.0.0.1:5601 -L 3000:127.0.0.1:3000 -L 9091:127.0.0.1:9091 user@сервер`

Примеры: 
![photo_2026-03-22 22 21 04](https://github.com/user-attachments/assets/8f1ff938-0d74-44cd-bde8-64a228eb2158)
![photo_2026-03-22 22 21 40](https://github.com/user-attachments/assets/39313b78-83d8-4f36-b864-618038610c1c)
![photo_2026-03-22 22 21 44](https://github.com/user-attachments/assets/dfeca58d-3e94-43b3-95f3-0bb8d8c196c9)


---

## 7. Структура проекта

```
src/
├── config.py         # Настройки (Pydantic)
├── database.py     # Подключение к PostgreSQL
├── models.py         # Peewee-модели
├── functions.py      # Инструменты LangChain (tools)
├── knowledge.py      # RAG: Qdrant, эмбеддинги
├── prompts.py        # Системный промпт
├── llm.py            # Клиент чата (OpenAI-совместимый)
├── observability.py  # Elasticsearch, Prometheus
└── main.py           # Точка входа, CLI, сессия
```

---

## 8. Зависимости

См. `requirements.txt` в корне проекта; образ приложения собирается из `Dockerfile`.
