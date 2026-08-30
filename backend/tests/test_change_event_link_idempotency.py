from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401
from app.db.database import Base
from app.models.change_events import (
    ChangeEntityLinkType,
)
from app.repositories.change_event_repository import (
    _upsert_link,
)


def test_upsert_link_does_not_duplicate_pending_link(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'link-idempotency.db').as_posix()}"
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    try:
        with Session(engine) as db_session:
            first = _upsert_link(
                db_session,
                event_id="change-event:test",
                entity_id="entity:test",
                link_type=(ChangeEntityLinkType.EXPLICIT),
                confidence=1.0,
                reason="First explicit link.",
                snapshot_id="snapshot:test",
                tenant_id=TEST_TENANT,
            )

            second = _upsert_link(
                db_session,
                event_id="change-event:test",
                entity_id="entity:test",
                link_type=(ChangeEntityLinkType.EXPLICIT),
                confidence=1.0,
                reason="Same explicit link again.",
                snapshot_id="snapshot:test",
                tenant_id=TEST_TENANT,
            )

            assert first is second

            db_session.flush()
    finally:
        engine.dispose()
