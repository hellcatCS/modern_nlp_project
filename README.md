# Restaurant Bot MVP

MVP чат-бота для автоматизации коммуникации ресторана.

## Запуск

1. Скопируйте `.env.example` в `.env` и укажите `OPENAI_API_KEY`:

```bash
cp .env.example .env
```

2. Запустите через Docker Compose:

```bash
docker compose run --rm app
```

Для чистого старта БД/индекса (fresh reset):

```bash
docker compose down -v
docker compose run --rm app
```

## Функционал

- Общение с LLM от имени менеджера ресторана
- RAG по загруженным документам (md/txt/json/pdf) + sample набор в репозитории
- Управление наборами знаний через CLI-команды
- Бронирование столиков с интервалом 2 часа и проверкой пересечений
- Отмена бронирований по `booking_id` (случайный буквенно-цифровой код, 7 символов)
- Передача диалога менеджеру при необходимости

## CLI-команды

- `/help`
- `/upload <path> [set_name]`
- `/list_docs`
- `/list_sets`
- `/activate_set <set_id>`
- `/reindex [set_id]`

Примечание: для вопросов по меню ассистент может делать до 3 последовательных retrieval-запросов, прежде чем предлагать эскалацию.

## Структура

```
src/
├── config.py         # Настройки (Pydantic)
├── database.py     # Подключение к PostgreSQL
├── models.py         # модели
├── functions.py      # Инструменты LangChain (tools)
├── knowledge.py      # RAG: Qdrant, эмбеддинги
├── prompts.py        # Системный промпт
├── llm.py            # Клиент чата (OpenAI-совместимый)
├── observability.py  # Elasticsearch, Prometheus
└── main.py           # Точка входа, CLI, сессия
```
