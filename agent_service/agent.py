"""The custom agentic loop, per the project spec: no framework (no
LangChain) -- a plain loop against the Claude Messages API using tool use.
User question -> model optionally calls get_schema -> model writes SQL via
run_query -> on a tool error the model sees the real error message and can
retry with corrected SQL -> model synthesizes a final natural-language
answer. The last successfully-run query is returned alongside the answer
so the caller (the FastAPI endpoint, eventually the dashboard) can surface
exactly what ran, per the spec's transparency requirement.
"""

from __future__ import annotations

import anthropic

from agent_service import tools
from db.config import get_settings

MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are a read-only NBA stats analyst with access to a Postgres \
database via two tools: get_schema and run_query. Always ground your answers in \
real query results -- never guess at numbers. Call get_schema first if you are not \
already certain of the exact table/column names. Write one SELECT at a time via \
run_query; if it returns an error, read the error and fix the query rather than \
giving up. When you have your answer, respond with a concise, direct natural- \
language answer to the user's question -- don't describe your process, just answer."""


class AgentError(RuntimeError):
    """Raised when the loop can't produce an answer (e.g. iteration cap hit)."""


def ask(question: str) -> dict:
    """Returns {"answer": str, "sql": str | None, "rows": list | None}.
    sql/rows reflect the last successfully-run query, or None if the
    model answered without needing one."""
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    messages: list[dict] = [{"role": "user", "content": question}]
    last_sql: str | None = None
    last_rows: list | None = None

    for _ in range(MAX_TOOL_ITERATIONS):
        # Streamed (not create()) since MAX_TOKENS is high enough that a
        # non-streaming call risks the SDK's own timeout guard.
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            tools=tools.TOOL_DEFINITIONS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "refusal":
            return {"answer": "I can't answer that question.", "sql": last_sql, "rows": last_rows}

        if response.stop_reason != "tool_use":
            answer = "".join(block.text for block in response.content if block.type == "text")
            return {"answer": answer, "sql": last_sql, "rows": last_rows}

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "get_schema":
                result = tools.get_schema()
            elif block.name == "run_query":
                result = tools.run_query(block.input.get("sql", ""))
                if isinstance(result, dict) and "sql" in result:
                    last_sql = result["sql"]
                    last_rows = result["rows"]
            else:
                result = {"error": f"Unknown tool {block.name}"}

            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
            )
        messages.append({"role": "user", "content": tool_results})

    raise AgentError(f"Did not reach a final answer within {MAX_TOOL_ITERATIONS} tool-use turns")
