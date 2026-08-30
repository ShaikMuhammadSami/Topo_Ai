import os
from collections.abc import Generator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATABASE_PATH = DATA_DIR / "topo.db"

RAW_DATABASE_URL = os.getenv(
    "TOPO_DATABASE_URL",
    f"sqlite:///{DEFAULT_DATABASE_PATH}",
)


def _synchronous_database_url(database_url: str) -> str:
    """Select psycopg 3 for unqualified synchronous PostgreSQL URLs."""
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix(
            "postgres://"
        )
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix(
            "postgresql://"
        )
    return database_url


DATABASE_URL = _synchronous_database_url(RAW_DATABASE_URL)

connect_args: dict[str, object] = {}

if make_url(DATABASE_URL).get_backend_name() == "sqlite":
    connect_args["check_same_thread"] = False


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def init_db(*, bind: Engine | None = None) -> None:
    """
    Initialize an intentional SQLite database or verify production authority.

    Disposable/local SQLite remains metadata-created for compatibility. Every
    non-SQLite deployment is migration-authoritative and must already be at
    the application's single Alembic head.
    """
    from app.db import models  # noqa: F401

    target = bind or engine
    if target.dialect.name == "sqlite":
        Base.metadata.create_all(bind=target)
        return

    from app.db.schema_management import verify_database_revision

    verify_database_revision(target)


def get_session(request: Request) -> Generator[Session, None, None]:
    """
    Provide one database session per API request.
    """
    with request.app.state.session_factory() as session:
        yield session
