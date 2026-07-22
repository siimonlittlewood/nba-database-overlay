from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "nba"
    postgres_password: str = "nba"
    postgres_db: str = "nba"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    # Phase 4 agent service -- a SEPARATE, DB-level-restricted role, not the
    # owner connection above. "changeme-dev-only" is fine for a local
    # docker-compose Postgres only; override via env for anything else.
    anthropic_api_key: str | None = None
    agent_db_user: str = "agent_readonly"
    agent_db_password: str = "changeme-dev-only"
    agent_row_limit: int = 200
    agent_statement_timeout_ms: int = 5000

    # Phase 2 dashboard -- where it reaches the agent service's /ask endpoint.
    agent_service_url: str = "http://localhost:8000"
    # If unset, the dashboard has no password gate (fine for local dev).
    # Set this before deploying publicly -- every question costs real
    # Anthropic API usage, so an open deployment is an open tab.
    dashboard_password: str | None = None

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def agent_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.agent_db_user}:{self.agent_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
