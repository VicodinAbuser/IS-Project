"""Application settings. Override any value with an environment variable or a backend/.env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Oracle connection. DSN format is host:port/service_name.
    # Oracle AI Database 26ai Free uses the pluggable database FREEPDB1.
    oracle_user: str = "inventory"
    oracle_password: str = "inventory123"
    oracle_dsn: str = "localhost:1521/FREEPDB1"

    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    # Browser origins allowed to call this API: the local Angular dev server, plus any
    # Vercel deployment (https://<anything>.vercel.app). Add your own domain here if you use one.
    cors_origins: list[str] = ["http://localhost:4200"]
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
