# tests/conftest.py
import pytest
from app.db.database import SessionLocal  # Update this import to match your database setup


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()