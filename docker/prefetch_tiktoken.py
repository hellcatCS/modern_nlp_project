#!/usr/bin/env python3
"""
Скачивает файлы кодировок tiktoken при docker build.
На рантайме контейнер может работать без исходящего интернета к Azure Blob.
"""
from __future__ import annotations

import os

# Должен совпадать с TIKTOKEN_CACHE_DIR в Dockerfile
os.environ.setdefault("TIKTOKEN_CACHE_DIR", "/app/.cache/tiktoken")

import tiktoken  # noqa: E402


def main() -> None:
    # Прямая подгрузка BPE (как в трейсбеке cl100k_base)
    for enc_name in ("cl100k_base", "o200k_base"):
        try:
            tiktoken.get_encoding(enc_name)
        except KeyError:
            pass

    # Тот же путь, что LangChain OpenAI при embed_documents / чате
    for model in (
        "gpt-4o-mini",
        "text-embedding-3-small",
    ):
        try:
            tiktoken.encoding_for_model(model)
        except Exception as exc:  # noqa: BLE001
            print(f"prefetch: encoding_for_model({model!r}) пропущен: {exc}")


if __name__ == "__main__":
    main()
