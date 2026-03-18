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

## Функционал

- Общение с LLM от имени менеджера ресторана
- Бронирование столиков (заглушка)
- Отмена бронирований (заглушка)
- Передача диалога менеджеру при необходимости

## Структура

```
src/
├── config.py     # Конфигурация
├── database.py   # Работа с PostgreSQL
├── models.py     # SQLAlchemy модели
├── functions.py  # Function calling инструменты
├── prompts.py    # Системный промпт
├── llm.py        # Клиент OpenAI
└── main.py       # CLI интерфейс
```
