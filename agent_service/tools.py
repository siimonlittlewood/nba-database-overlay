"""The two tools exposed to the model, per the project spec: get_schema()
and run_query(sql). run_query is where sql_guard's validation actually
gets applied -- there is no other path to the database from agent.py.
"""

from __future__ import annotations

import datetime
import decimal
import logging
from typing import Any

from sqlalchemy import text

from agent_service import schema
from agent_service.db import engine
from agent_service.sql_guard import UnsafeQueryError, validate_and_limit
from db.config import get_settings

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "name": "get_schema",
        "description": (
            "Returns a description of the database schema: tables, columns, "
            "and important notes about data coverage/limitations. Call this "
            "before writing SQL if you're not already certain of the exact "
            "table/column names."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_query",
        "description": (
            "Executes a single read-only SQL SELECT statement against the "
            "database and returns the resulting rows. Only SELECT (including "
            "WITH ... SELECT) is permitted -- anything else is rejected "
            "before execution, and a row limit is enforced automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement."},
            },
            "required": ["sql"],
        },
    },
]


def _json_safe(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def get_schema() -> str:
    return schema.get_schema()


def run_query(sql: str) -> dict:
    """Returns {"sql": <the query actually executed, after limit
    enforcement>, "rows": [...]} on success, or {"error": "..."} on
    failure -- callers (agent.py) forward either shape back to the model
    as a tool_result so it can see and self-correct from a real error
    message, per the spec's self-correction requirement."""
    settings = get_settings()
    try:
        safe_sql = validate_and_limit(sql, row_limit=settings.agent_row_limit)
    except UnsafeQueryError as exc:
        return {"error": str(exc)}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            rows = [{k: _json_safe(v) for k, v in row.items()} for row in result.mappings()]
    except Exception as exc:
        logger.exception("run_query failed against the database")
        return {"error": str(exc)}

    return {"sql": safe_sql, "rows": rows}
