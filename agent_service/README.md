# Agent service

Phase 4 — FastAPI text-to-SQL service. Exposes `POST /ask`.

Run locally: `uvicorn agent_service.main:app --reload --port 8000`

Safety layers (all independent of each other, not just app-level checks):
- `agent_readonly` Postgres role (see the Alembic migration that created it) — SELECT-only at the database level, plus a statement timeout.
- `agent_service/sql_guard.py` — parses generated SQL with `sqlglot`, rejects anything that isn't a single SELECT, enforces a row limit.

Requires `ANTHROPIC_API_KEY` and `AGENT_DB_PASSWORD` in `.env` (see `.env.example`).
