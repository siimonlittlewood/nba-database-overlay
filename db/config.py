from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "nba"
    postgres_password: str = "nba"
    postgres_db: str = "nba"
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    # e.g. "sslmode=require&channel_binding=require" for a hosted provider
    # (Neon, Supabase) that mandates TLS -- unused (empty) for local docker-
    # compose Postgres, which doesn't need it.
    postgres_query: str = ""

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
    # Shared secret between the dashboard and agent_service. If unset, the
    # agent service accepts requests with no auth (fine for local dev, where
    # both run on localhost) -- set this before deploying publicly, since the
    # agent service's URL is otherwise reachable directly, bypassing the
    # dashboard password entirely.
    agent_api_key: str | None = None
    # If unset, the dashboard has no password gate (fine for local dev).
    # Set this before deploying publicly -- every question costs real
    # Anthropic API usage, so an open deployment is an open tab.
    dashboard_password: str | None = None

    # False for the public deployment's hosted DB, which omits play_by_play
    # (3GB, doesn't fit a free-tier hosted Postgres). True locally, where
    # the full table exists. Read by both agent_service (so it explains the
    # gap instead of erroring on a missing table) and the dashboard (so the
    # human user sees the same caveat up front).
    play_by_play_available: bool = True

    def _url(self, user: str, password: str) -> str:
        base = f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        return f"{base}?{self.postgres_query}" if self.postgres_query else base

    @property
    def database_url(self) -> str:
        return self._url(self.postgres_user, self.postgres_password)

    @property
    def agent_database_url(self) -> str:
        return self._url(self.agent_db_user, self.agent_db_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
