"""Application settings. Override any value with an environment variable or a backend/.env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Oracle connection. DSN format is host:port/service_name (the PLUGGABLE database).
    #   Oracle 26ai Free: localhost:1521/FREEPDB1   Oracle 21c: usually localhost:1521/ORCLPDB
    # setup_db.py --create-user asks for it and saves it in backend/.env.
    oracle_user: str = "inventory"
    oracle_password: str = "inventory123"
    oracle_dsn: str = "localhost:1521/FREEPDB1"

    # Login sessions. The signed token travels in an HttpOnly cookie, so page scripts can't read it.
    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    cookie_name: str = "ims_session"
    # Secure = the browser only sends the cookie over HTTPS (http://localhost also counts as secure).
    # Set COOKIE_SECURE=false only if you open the website on another computer over plain http.
    cookie_secure: bool = True

    # ---- Business rules (used by app/services) ----
    payment_timeout_minutes: int = 30      # unpaid orders older than this are cancelled and their stock released
    max_failed_logins: int = 5             # wrong passwords in a row before the account is locked ...
    lock_minutes: int = 15                 # ... for this many minutes
    max_items_per_order: int = 20          # different products in one order

    # Browser origins allowed to call this API directly. Normally empty: the website reaches
    # the API through the same address (/api), via the Angular dev proxy locally or the Vercel
    # rewrite online, so no cross-origin access is needed.
    cors_origins: list[str] = []

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
