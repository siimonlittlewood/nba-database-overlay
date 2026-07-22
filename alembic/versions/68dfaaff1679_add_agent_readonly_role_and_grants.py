"""add agent_readonly role and grants

Revision ID: 68dfaaff1679
Revises: 72da97253922
Create Date: 2026-07-22 09:13:06.254852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from db.config import get_settings


# revision identifiers, used by Alembic.
revision: str = '68dfaaff1679'
down_revision: Union[str, Sequence[str], None] = '72da97253922'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Creates the Phase-4 agent's DB-level-restricted role. This is the
    actual safety enforcement the project spec calls "non-negotiable" --
    the role physically cannot INSERT/UPDATE/DELETE/DDL, independent of
    any app-level check in agent_service/sql_guard.py. Reads db_name/
    password from Settings (same env-driven config as everything else in
    this project) rather than hardcoding them, so this isn't tied to one
    database name or a committed secret.
    """
    settings = get_settings()
    role = settings.agent_db_user
    password = settings.agent_db_password.replace("'", "''")
    db_name = settings.postgres_db

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} WITH LOGIN PASSWORD '{password}';
            END IF;
        END
        $$;
        """
    )
    # Re-applied every run so a changed AGENT_DB_PASSWORD env value takes
    # effect on the next migration, not just on first creation.
    op.execute(f"ALTER ROLE {role} WITH PASSWORD '{password}'")
    op.execute(f"GRANT CONNECT ON DATABASE {db_name} TO {role}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {role}")
    op.execute(f"ALTER ROLE {role} SET statement_timeout = '{settings.agent_statement_timeout_ms}'")


def downgrade() -> None:
    """Downgrade schema."""
    settings = get_settings()
    role = settings.agent_db_user
    db_name = settings.postgres_db

    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM {role}")
    op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {role}")
    op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {role}")
    op.execute(f"REVOKE CONNECT ON DATABASE {db_name} FROM {role}")
    op.execute(f"DROP ROLE IF EXISTS {role}")
