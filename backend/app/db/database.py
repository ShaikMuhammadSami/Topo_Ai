import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATABASE_PATH = DATA_DIR / "topo.db"

DATABASE_URL = os.getenv(
    "TOPO_DATABASE_URL",
    f"sqlite:///{DEFAULT_DATABASE_PATH}",
)

connect_args: dict[str, object] = {}

if DATABASE_URL.startswith("sqlite"):
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


def init_db() -> None:
    """
    Create database tables that do not already exist.
    """
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """
    Provide one database session per API request.
    """
    with SessionLocal() as session:
        yield session