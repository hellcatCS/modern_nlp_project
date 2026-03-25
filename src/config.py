import os
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # В режиме USE_VLLM_LLM=true: чат → vLLM (VLLM_BASE_URL), эмбеддинги → HF (HF_EMBEDDING_MODEL), без OpenAI API.
    # Переменная окружения: USE_VLLM_LLM (без validation_alias — надёжнее читается из Docker/env).
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    use_vllm_llm: bool = False
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    # Путь к весам на ВМ (для документации / запуска vllm вручную; сам сервер поднимается отдельно)
    vllm_model_path: str = "/home/aesemikin/models/Qwen3-30B-A3B"
    # Имя модели в запросах к vLLM (как в --served-model-name или имя каталога с весами)
    vllm_model: str = "Qwen3-30B-A3B"
    vllm_api_key: str = "EMPTY"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "text-embedding-3-small"
    # Локальный fallback при блокировке региона OpenAI (скачивается с Hugging Face при первом срабатывании)
    hf_embedding_model: str = "cointegrated/rubert-tiny2"
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5433/restaurant_bot"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection_prefix: str = "restaurant_knowledge"
    rag_top_k: int = 7
    rag_min_score: float = 0.05

    # Наблюдаемость: Elasticsearch/Kibana + Prometheus/Grafana (по умолчанию включено; выключите в .env)
    observability_enabled: bool = True
    elasticsearch_enabled: bool = True
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "restaurant-bot-logs"
    prometheus_metrics_enabled: bool = True
    prometheus_metrics_host: str = "0.0.0.0"
    prometheus_metrics_port: int = 9090

    @model_validator(mode="after")
    def _vllm_typo_and_require_key(self) -> Self:
        # Прямое чтение os.environ: в Docker pydantic иногда не подхватывает bool из env_file
        if _env_truthy("USE_VLLM_LLM"):
            object.__setattr__(self, "use_vllm_llm", True)
        # Опечатка USE_VVLM_LLM в .env
        if not self.use_vllm_llm and _env_truthy("USE_VVLM_LLM") and not _env_truthy("USE_VLLM_LLM"):
            object.__setattr__(self, "use_vllm_llm", True)
        if _env_truthy("OBSERVABILITY_ENABLED"):
            object.__setattr__(self, "observability_enabled", True)
        if _env_truthy("ELASTICSEARCH_ENABLED"):
            object.__setattr__(self, "elasticsearch_enabled", True)
        if _env_truthy("PROMETHEUS_METRICS_ENABLED"):
            object.__setattr__(self, "prometheus_metrics_enabled", True)

        if self.use_vllm_llm:
            return self
        if not (self.openai_api_key or "").strip():
            raise ValueError(
                "Укажите OPENAI_API_KEY в .env или включите USE_VLLM_LLM=true для локального vLLM."
            )
        return self


settings = Settings()
