# Dashboard

Phase 2 — a single-page Streamlit app: a chat panel calling `agent_service/`
over HTTP. Deliberately scoped to just this -- the agent is the point of the
project, not a multi-page BI dashboard.

Run locally: `streamlit run dashboard/app.py` (start `agent_service` first --
`uvicorn agent_service.main:app --port 8000` -- or the chat will report it
can't reach it).

**Before deploying publicly:** set `DASHBOARD_PASSWORD` (unset = no gate,
fine for local dev) and a hard spending limit on the Anthropic API key in
the Console -- every question here costs real API usage, so an open
deployment is an open tab on your account.
