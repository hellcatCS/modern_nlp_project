"""Минимальные переменные окружения для загрузки Settings в тестах без .env."""
import os

# pydantic-settings требует ключ; значение не используется в unit-тестах observability.
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-used")
