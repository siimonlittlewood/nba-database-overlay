"""A SEPARATE engine/session from db/session.py's owner-role connection.
The agent must never touch the read-write engine -- it only ever talks to
Postgres through the agent_readonly role (see the Alembic migration that
created it), so a bug in the agent's SQL generation or sql_guard.py is
still contained by the database itself, not just application code.
"""

from __future__ import annotations

from sqlalchemy import create_engine

from db.config import get_settings

engine = create_engine(get_settings().agent_database_url, future=True)
