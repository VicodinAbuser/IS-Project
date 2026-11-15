"""Application settings. Override any value with an environment variable or a backend/.env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Oracle connection. DSN format is host:port/service_name (the PLUGGABLE database).
    #   Oracle 26ai Free: localhost:1521/ORCLPDB   Oracle 21c: usually localhost:1521/ORCLPDB
    # setup_db.py --create-user asks for it and saves it in backend/.env.
    oracle_user: str = "inventory"
    oracle_password: str = "inventory123"
    oracle_dsn: str = "localhost:1521/ORCLPDB"

    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    # Browser origins allowed to call this API: the local Angular dev server, plus any
    # Vercel deployment (https://<anything>.vercel.app). Add your own domain here if you use one.
    cors_origins: list[str] = ["http://localhost:4200"]
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
