import pytest

from agent_service.sql_guard import UnsafeQueryError, validate_and_limit


def test_plain_select_gets_limit_injected():
    result = validate_and_limit("SELECT * FROM teams", row_limit=200)
    assert "LIMIT 200" in result


def test_select_with_acceptable_limit_is_untouched():
    result = validate_and_limit("SELECT * FROM teams LIMIT 50", row_limit=200)
    assert "LIMIT 50" in result
    assert "LIMIT 200" not in result


def test_select_with_excessive_limit_is_clamped():
    result = validate_and_limit("SELECT * FROM teams LIMIT 100000", row_limit=200)
    assert "LIMIT 200" in result
    assert "100000" not in result


def test_cte_select_is_allowed():
    result = validate_and_limit("WITH x AS (SELECT * FROM teams) SELECT * FROM x", row_limit=200)
    assert "LIMIT 200" in result


def test_rejects_insert():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("INSERT INTO teams (id) VALUES (1)", row_limit=200)


def test_rejects_delete():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("DELETE FROM teams", row_limit=200)


def test_rejects_drop():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("DROP TABLE teams", row_limit=200)


def test_rejects_multiple_statements():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("SELECT * FROM teams; SELECT * FROM players", row_limit=200)


def test_rejects_select_followed_by_drop():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("SELECT * FROM teams; DROP TABLE teams;", row_limit=200)


def test_rejects_unparseable_input():
    with pytest.raises(UnsafeQueryError):
        validate_and_limit("this is not sql at all @#$%", row_limit=200)
