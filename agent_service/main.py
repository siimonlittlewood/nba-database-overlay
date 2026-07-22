from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent_service.agent import AgentError, ask
from db.config import get_settings

app = FastAPI(title="NBA stats agent service")


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _check_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """No-op if AGENT_API_KEY is unset (local dev, dashboard and agent_service
    both on localhost). Set it before deploying publicly -- otherwise this
    service's URL is reachable directly over the internet, bypassing the
    dashboard's own password gate entirely."""
    required = get_settings().agent_api_key
    if not required:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, required):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sql: str | None
    rows: list | None


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(_check_api_key)])
def ask_endpoint(request: AskRequest) -> AskResponse:
    try:
        result = ask(request.question)
    except AgentError as exc:
        return AskResponse(answer=f"Couldn't reach an answer: {exc}", sql=None, rows=None)
    return AskResponse(**result)
