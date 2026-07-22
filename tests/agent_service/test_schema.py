from types import SimpleNamespace

from agent_service import schema


def test_get_schema_includes_play_by_play_when_available(monkeypatch):
    monkeypatch.setattr(schema, "get_settings", lambda: SimpleNamespace(play_by_play_available=True))
    result = schema.get_schema()
    assert "play_by_play(id, game_id" in result
    assert "NOT AVAILABLE" not in result


def test_get_schema_notes_play_by_play_unavailable(monkeypatch):
    monkeypatch.setattr(schema, "get_settings", lambda: SimpleNamespace(play_by_play_available=False))
    result = schema.get_schema()
    assert "NOT AVAILABLE in this deployment" in result
    assert "play_by_play(id, game_id" not in result
