from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent_service import main


def _client() -> TestClient:
    return TestClient(main.app)


def test_ask_succeeds_with_no_api_key_configured(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(agent_api_key=None))
    monkeypatch.setattr(main, "ask", lambda question: {"answer": "42", "sql": None, "rows": None})

    response = _client().post("/ask", json={"question": "how many teams?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "42"


def test_ask_rejects_missing_api_key_when_configured(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(agent_api_key="secret123"))
    monkeypatch.setattr(main, "ask", lambda question: {"answer": "42", "sql": None, "rows": None})

    response = _client().post("/ask", json={"question": "how many teams?"})

    assert response.status_code == 401


def test_ask_rejects_wrong_api_key(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(agent_api_key="secret123"))
    monkeypatch.setattr(main, "ask", lambda question: {"answer": "42", "sql": None, "rows": None})

    response = _client().post(
        "/ask", json={"question": "how many teams?"}, headers={"X-API-Key": "wrong"}
    )

    assert response.status_code == 401


def test_ask_accepts_correct_api_key(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(agent_api_key="secret123"))
    monkeypatch.setattr(main, "ask", lambda question: {"answer": "42", "sql": None, "rows": None})

    response = _client().post(
        "/ask", json={"question": "how many teams?"}, headers={"X-API-Key": "secret123"}
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "42"
