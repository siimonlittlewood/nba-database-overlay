import pytest
from sqlalchemy.orm import Session

from db.session import engine


@pytest.fixture()
def db_session():
    """Yields a Session bound to a connection-level transaction that's
    rolled back after the test, so tests never leave rows behind in the
    shared docker-compose Postgres instance."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
