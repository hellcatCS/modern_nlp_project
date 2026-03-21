from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "text-embedding-3-small"
    database_url: str = "postgresql://postgres:postgres@db:5432/restaurant_bot"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_prefix: str = "restaurant_knowledge"
    rag_top_k: int = 7
    rag_min_score: float = 0.05

    class Config:
        env_file = ".env"


settings = Settings()
