from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    database_url: str = "postgresql://postgres:postgres@db:5432/restaurant_bot"

    class Config:
        env_file = ".env"


settings = Settings()
