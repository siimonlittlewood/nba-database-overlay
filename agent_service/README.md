# Agent service

Phase 4 — FastAPI text-to-SQL service. Exposes `POST /ask`.

Run locally: `uvicorn agent_service.main:app --reload --port 8000`

Safety layers (all independent of each other, not just app-level checks):
- `agent_readonly` Postgres role (see the Alembic migration that created it) — SELECT-only at the database level, plus a statement timeout.
- `agent_service/sql_guard.py` — parses generated SQL with `sqlglot`, rejects anything that isn't a single SELECT, enforces a row limit.
- `AGENT_API_KEY` — a shared secret checked on `/ask` (via the `X-API-Key` header). The dashboard's own password gate only protects the Streamlit UI; without this, anyone who finds this service's URL directly could call `/ask` themselves, bypassing that gate entirely. No-op if unset (fine for local dev where both run on localhost).

Requires `ANTHROPIC_API_KEY` and `AGENT_DB_PASSWORD` in `.env` (see `.env.example`). Set `AGENT_API_KEY` too before deploying publicly.

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
   password), and `AGENT_API_KEY` (any long random string — generate one with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Note this service
   is never given the owner Postgres credentials at all — `agent_database_url` only
   needs `AGENT_DB_USER`/`AGENT_DB_PASSWORD`.
4. Once deployed, smoke-test with `curl https://<your-service>.onrender.com/` (should
   return `{"status": "ok"}`) and then a real question against `/ask` — without the
   `X-API-Key` header it should now 401 once `AGENT_API_KEY` is set.
5. Point the dashboard's `AGENT_SERVICE_URL` and `AGENT_API_KEY` secrets at this
   service's Render URL and the same key from step 3.

Free-tier caveat: the service spins down after 15 minutes of inactivity, so the first
request after idle time will be slow (cold start, ~30-60s) before responding normally.
