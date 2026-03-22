"""Логирование (Elasticsearch/Kibana) и метрики Prometheus для Grafana."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter, Histogram, REGISTRY, start_http_server

from src.config import settings

_observability_lock = threading.Lock()
_observability_ready = False
_prometheus_started = False

_es_handler: logging.Handler | None = None

# Метрики (регистрируются один раз при включённой наблюдаемости)
chat_messages_total: Counter | None = None
cli_commands_total: Counter | None = None
llm_rounds_total: Counter | None = None
llm_tool_calls_total: Counter | None = None
llm_escalations_total: Counter | None = None
llm_errors_total: Counter | None = None
llm_round_duration_seconds: Histogram | None = None


def log_record_to_elasticsearch_document(record: logging.LogRecord) -> dict[str, Any]:
    """Преобразует LogRecord в документ для Elasticsearch (ECS-подобные поля)."""
    ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "@timestamp": ts,
        "message": record.getMessage(),
        "log": {
            "level": record.levelname,
            "logger": record.name,
        },
        "process": {"pid": record.process},
        "thread": {"name": record.threadName, "id": record.thread},
    }
    if record.exc_info and record.exc_text:
        payload["error"] = {"message": record.exc_text[:8000]}
    if record.pathname:
        payload["log"]["origin"] = {
            "file": {"name": record.filename, "line": record.lineno, "path": record.pathname}
        }
    return payload


def _silence_elasticsearch_client_loggers() -> None:
    """Иначе INFO от elastic_transport при HTTP-запросе снова попадает в root → рекурсия в ElasticsearchLogHandler."""
    for name in ("elastic_transport", "elasticsearch", "elastic_transport.transport"):
        logging.getLogger(name).setLevel(logging.WARNING)


class ElasticsearchLogHandler(logging.Handler):
    """Отправка логов в Elasticsearch (индекс по дням: prefix-YYYY.MM.DD)."""

    def __init__(self, elasticsearch_url: str, index_prefix: str, level: int = logging.INFO):
        super().__init__(level=level)
        from elasticsearch import Elasticsearch

        self._client = Elasticsearch(elasticsearch_url)
        self._index_prefix = index_prefix.rstrip("-")
        self._emit_guard = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        # Повторный вход: index() → логирование клиента → снова emit → переполнение стека
        if getattr(self._emit_guard, "active", False):
            return
        self._emit_guard.active = True
        try:
            doc = log_record_to_elasticsearch_document(record)
            day = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y.%m.%d")
            index_name = f"{self._index_prefix}-{day}"
            self._client.index(index=index_name, document=doc)
        except Exception:
            self.handleError(record)
        finally:
            self._emit_guard.active = False


def _register_metrics() -> None:
    global chat_messages_total, cli_commands_total, llm_rounds_total, llm_tool_calls_total
    global llm_escalations_total, llm_errors_total, llm_round_duration_seconds

    chat_messages_total = Counter(
        "chat_user_messages_total",
        "Количество пользовательских сообщений в чате (не команды CLI).",
        registry=REGISTRY,
    )
    cli_commands_total = Counter(
        "cli_commands_total",
        "Количество обработанных CLI-команд.",
        ["command"],
        registry=REGISTRY,
    )
    llm_rounds_total = Counter(
        "llm_rounds_total",
        "Завершённые раунды общения с LLM (один ответ ассистента).",
        registry=REGISTRY,
    )
    llm_tool_calls_total = Counter(
        "llm_tool_calls_total",
        "Вызовы инструментов (function calling) по имени.",
        ["tool_name"],
        registry=REGISTRY,
    )
    llm_escalations_total = Counter(
        "llm_escalations_total",
        "Передачи диалога менеджеру после ответа LLM.",
        registry=REGISTRY,
    )
    llm_errors_total = Counter(
        "llm_errors_total",
        "Ошибки при обращении к LLM или обработке ответа.",
        ["stage"],
        registry=REGISTRY,
    )
    llm_round_duration_seconds = Histogram(
        "llm_round_duration_seconds",
        "Длительность одного раунда LLM (invoke + tool loop), секунды.",
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
        registry=REGISTRY,
    )


def _start_prometheus_http() -> None:
    global _prometheus_started
    if _prometheus_started:
        return
    host = settings.prometheus_metrics_host
    port = settings.prometheus_metrics_port
    start_http_server(port, addr=host)
    _prometheus_started = True


def setup_observability() -> None:
    """Инициализация логирования в ES и HTTP /metrics для Prometheus. Идемпотентна."""
    global _observability_ready, _es_handler

    if not settings.observability_enabled:
        return

    with _observability_lock:
        if _observability_ready:
            return

        if settings.prometheus_metrics_enabled:
            _register_metrics()
            _start_prometheus_http()

        if settings.elasticsearch_enabled:
            _silence_elasticsearch_client_loggers()
            _es_handler = ElasticsearchLogHandler(
                settings.elasticsearch_url,
                settings.elasticsearch_index_prefix,
                level=logging.INFO,
            )
            root = logging.getLogger()
            root.addHandler(_es_handler)

        _observability_ready = True


def record_user_message() -> None:
    if chat_messages_total:
        chat_messages_total.inc()


def record_cli_command(command: str) -> None:
    if cli_commands_total:
        cli_commands_total.labels(command=command).inc()


def record_llm_round(duration_s: float, tool_names: list[str], escalated: bool) -> None:
    if llm_round_duration_seconds is not None:
        llm_round_duration_seconds.observe(duration_s)
    if llm_rounds_total:
        llm_rounds_total.inc()
    if llm_tool_calls_total:
        for name in tool_names:
            llm_tool_calls_total.labels(tool_name=name).inc()
    if escalated and llm_escalations_total:
        llm_escalations_total.inc()


def record_llm_error(stage: str) -> None:
    if llm_errors_total:
        llm_errors_total.labels(stage=stage).inc()
