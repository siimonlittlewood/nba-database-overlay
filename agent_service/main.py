from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from agent_service.agent import AgentError, ask

app = FastAPI(title="NBA stats agent service")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sql: str | None
    rows: list | None


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest) -> AskResponse:
    try:
        result = ask(request.question)
    except AgentError as exc:
        return AskResponse(answer=f"Couldn't reach an answer: {exc}", sql=None, rows=None)
    return AskResponse(**result)
