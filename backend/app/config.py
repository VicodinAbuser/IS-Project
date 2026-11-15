"""Application settings. Override any value with an environment variable or a .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SQLite needs no setup for the demo. For PostgreSQL use e.g.
    # DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/inventory
    database_url: str = "sqlite:///./inventory.db"
    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:4200"]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
