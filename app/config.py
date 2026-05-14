from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class Settings(BaseSettings):
    # Community Configuration (used to seed default client on startup)
    client_name: str = "default"
    community_name: str = ""
    community_description: str = ""
    invite_link: str = ""
    agent_name: str = ""
    agent_tone: str = "warm and conversational"

    # Timing Configuration
    follow_up_delay_mins: int = 30
    abandon_after_hours: int = 24
    nudge_delay_mins: int = 30
    timeout_hours: int = 24
    engagement_threshold: float = 0.3
    engagement_days: int = 14

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "onboardme"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    database_url: Optional[str] = None

    # AI Provider (currently Groq, Claude ready for later)
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    # WhatsApp Bridge
    baileys_session_path: str = "./sessions"
    whatsapp_bridge_url: str = "http://localhost:3000"
    human_escalation_whatsapp: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    admin_token: str = ""

    # Webhook secret for default client (used at startup for seeding)
    webhook_secret: str = ""

    # Optional links
    calendly_link: Optional[str] = None
    founder_stories_link: Optional[str] = None
    operator_session_link: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()

if settings.database_url:
    parsed_url = urlsplit(settings.database_url)
    query = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    clean_url = urlunsplit(parsed_url._replace(query=urlencode(query)))

    DATABASE_URL = clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    SYNC_DATABASE_URL = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    DATABASE_CONNECT_ARGS = {"ssl": True} if sslmode else {}
else:
    DATABASE_URL = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    SYNC_DATABASE_URL = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    DATABASE_CONNECT_ARGS = {}
