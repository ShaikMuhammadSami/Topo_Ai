from app.models.change_events import (
    ChangeEntityLinkType,
)
from app.repositories.change_event_repository import (
    _upsert_link,
)


def test_upsert_link_does_not_duplicate_pending_link(
    db_session,
) -> None:
    first = _upsert_link(
        db_session,
        event_id="change-event:test",
        entity_id="entity:test",
        link_type=(
            ChangeEntityLinkType.EXPLICIT
        ),
        confidence=1.0,
        reason="First explicit link.",
        snapshot_id="snapshot:test",
    )

    second = _upsert_link(
        db_session,
        event_id="change-event:test",
        entity_id="entity:test",
        link_type=(
            ChangeEntityLinkType.EXPLICIT
        ),
        confidence=1.0,
        reason="Same explicit link again.",
        snapshot_id="snapshot:test",
    )

    assert first is second

    db_session.flush()