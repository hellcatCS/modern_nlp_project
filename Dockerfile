FROM python:3.11-slim

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8
# Кеш tiktoken в образе — рантайм не тянет файлы с openaipublic.blob.core.windows.net
ENV TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

COPY docker/prefetch_tiktoken.py /tmp/prefetch_tiktoken.py
RUN mkdir -p /app/.cache/tiktoken && python /tmp/prefetch_tiktoken.py && rm /tmp/prefetch_tiktoken.py

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]
