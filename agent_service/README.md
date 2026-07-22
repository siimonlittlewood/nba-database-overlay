# Agent service

Phase 4 — FastAPI text-to-SQL service. Exposes `POST /ask`.

Run locally: `uvicorn agent_service.main:app --reload --port 8000`

Safety layers (all independent of each other, not just app-level checks):
- `agent_readonly` Postgres role (see the Alembic migration that created it) — SELECT-only at the database level, plus a statement timeout.
- `agent_service/sql_guard.py` — parses generated SQL with `sqlglot`, rejects anything that isn't a single SELECT, enforces a row limit.

Requires `ANTHROPIC_API_KEY` and `AGENT_DB_PASSWORD` in `.env` (see `.env.example`).

## Deploying (Render)

`render.yaml` at the repo root defines this as a Render web service (native Python
runtime, no Dockerfile needed). To deploy:

1. Push this repo to GitHub (already done).
2. In the Render dashboard: New -> Blueprint -> connect the GitHub repo. Render reads
   `render.yaml` and creates the `nba-agent-service` web service automatically.
3. Fill in the env vars marked `sync: false` when prompted (Render won't store these
   in the repo): `ANTHROPIC_API_KEY`, `POSTGRES_HOST` (the Neon host, e.g.
   `ep-old-field-a6nuhuuw-pooler.us-west-2.aws.neon.tech`), `POSTGRES_DB` (`neondb`),
   `AGENT_DB_PASSWORD` (the `agent_readonly` role's password — NOT the Neon owner
   password). Note this service is never given the owner Postgres credentials at all —
   `agent_database_url` only needs `AGENT_DB_USER`/`AGENT_DB_PASSWORD`.
4. Once deployed, smoke-test with `curl https://<your-service>.onrender.com/` (should
   return `{"status": "ok"}`) and then a real question against `/ask`.
5. Point the dashboard's `AGENT_SERVICE_URL` secret at this service's Render URL.

Free-tier caveat: the service spins down after 15 minutes of inactivity, so the first
request after idle time will be slow (cold start, ~30-60s) before responding normally.
