from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeSourceDeadLetterRecord,
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
    utc_now_iso,
)
from app.models.change_sources import (
    ChangeSourceDeliveryReceipt,
    ChangeSourceReplayResponse,
)
from app.repositories.change_event_repository import (
    ingest_change_event,
)
from app.services.external_change_normalizers import (
    normalize_azure_devops,
    normalize_github,
    normalize_gitlab,
    normalize_jenkins,
    normalize_terraform_cloud,
)
from app.services.github_source_file_enrichment import (
    GitHubSourceEvidenceProviderFactory,
    enrich_github_push_events,
    github_source_evidence_provider,
    unavailable_github_push_events,
)
from app.services.webhook_security import (
    resolve_secret,
    verify_basic_auth,
    verify_github,
    verify_gitlab_secret_token,
    verify_gitlab_signing_token,
    verify_terraform_cloud,
    verify_topo_hmac,
)


SAFE_HEADERS = {
    "content-type",
    "user-agent",
    "x-github-event",
    "x-github-delivery",
    "x-gitlab-event",
    "x-gitlab-event-uuid",
    "webhook-id",
    "webhook-timestamp",
    "idempotency-key",
    "x-tfe-notification-signature",
}


SENSITIVE_KEYS = {
    "authorization",
    "token",
    "secret",
    "password",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "api_key",
    "apikey",
}


def _redact(
    value: Any,
) -> Any:
    if isinstance(value, dict):
        result = {}

        for key, item in value.items():
            if (
                str(key).lower()
                in SENSITIVE_KEYS
            ):
                result[key] = (
                    "[REDACTED]"
                )

            else:
                result[key] = (
                    _redact(item)
                )

        return result

    if isinstance(value, list):
        return [
            _redact(item)
            for item in value
        ]

    return value


def _safe_headers(
    headers: dict[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value
        in headers.items()
        if key.lower()
        in SAFE_HEADERS
    }


def _header_map(
    headers: dict[str, str],
) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value
        in headers.items()
    }


def _event_type(
    *,
    source_type: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> str:
    lower = _header_map(
        headers
    )

    if source_type == "github":
        return lower.get(
            "x-github-event",
            "unknown",
        )

    if source_type == "gitlab":
        return (
            lower.get(
                "x-gitlab-event"
            )
            or str(
                payload.get(
                    "object_kind",
                    "unknown",
                )
            )
        )

    if source_type == (
        "azure_devops"
    ):
        return str(
            payload.get(
                "eventType",
                "unknown",
            )
        )

    if source_type == "jenkins":
        return str(
            payload.get(
                "event_type",
                "build",
            )
        )

    if source_type == (
        "terraform_cloud"
    ):
        notifications = (
            payload.get(
                "notifications"
            )
        )

        if (
            isinstance(
                notifications,
                list,
            )
            and notifications
            and isinstance(
                notifications[0],
                dict,
            )
        ):
            return str(
                notifications[0].get(
                    "trigger",
                    "notification",
                )
            )

        return "verification"

    return "unknown"


def _source_delivery_id(
    *,
    source_type: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    payload_hash: str,
) -> str:
    lower = _header_map(
        headers
    )

    if source_type == "github":
        return (
            lower.get(
                "x-github-delivery"
            )
            or payload_hash
        )

    if source_type == "gitlab":
        return (
            lower.get(
                "webhook-id"
            )
            or lower.get(
                "idempotency-key"
            )
            or lower.get(
                "x-gitlab-event-uuid"
            )
            or payload_hash
        )

    if source_type == (
        "azure_devops"
    ):
        return str(
            payload.get("id")
            or payload_hash
        )

    if source_type == "jenkins":
        return str(
            payload.get(
                "delivery_id"
            )
            or (
                f"{payload.get('job_name')}:"
                f"{payload.get('build_number')}:"
                f"{payload.get('status')}"
            )
        )

    if source_type == (
        "terraform_cloud"
    ):
        return str(
            payload.get(
                "run_id"
            )
            or payload.get(
                "notification_configuration_id"
            )
            or payload_hash
        )

    return payload_hash


def _verify(
    *,
    source: ChangeSourceRecord,
    body: bytes,
    headers: dict[str, str],
) -> None:
    secret = resolve_secret(
        source.secret_ref
    )

    lower = _header_map(
        headers
    )

    config = json.loads(
        source.config_json
        or "{}"
    )

    if source.source_type == "github":
        verify_github(
            secret=secret,
            body=body,
            signature=lower.get(
                "x-hub-signature-256"
            ),
        )

        return

    if source.source_type == "gitlab":
        auth_mode = str(
            config.get(
                "auth_mode",
                "signing",
            )
        ).lower()

        if auth_mode == "secret_token":
            verify_gitlab_secret_token(
                secret=secret,
                supplied_token=lower.get(
                    "x-gitlab-token"
                ),
            )

        else:
            verify_gitlab_signing_token(
                signing_token=secret,
                body=body,
                webhook_id=lower.get(
                    "webhook-id"
                ),
                timestamp=lower.get(
                    "webhook-timestamp"
                ),
                signature=lower.get(
                    "webhook-signature"
                ),
                maximum_age_seconds=int(
                    config.get(
                        "signature_max_age",
                        300,
                    )
                ),
            )

        return

    if (
        source.source_type
        == "terraform_cloud"
    ):
        verify_terraform_cloud(
            secret=secret,
            body=body,
            signature=lower.get(
                "x-tfe-notification-signature"
            ),
        )

        return

    if source.source_type == "jenkins":
        verify_topo_hmac(
            secret=secret,
            body=body,
            signature=lower.get(
                "x-topo-signature-256"
            ),
        )

        return

    if (
        source.source_type
        == "azure_devops"
    ):
        verify_basic_auth(
            username=str(
                config.get(
                    "username",
                    "topo-webhook",
                )
            ),
            secret=secret,
            authorization=lower.get(
                "authorization"
            ),
        )

        return

    raise ValueError(
        "Unsupported change source."
    )


def _normalize(
    *,
    source: ChangeSourceRecord,
    event_type: str,
    payload: dict[str, Any],
    github_provider_factory: GitHubSourceEvidenceProviderFactory = (
        github_source_evidence_provider
    ),
):
    config = json.loads(
        source.config_json
        or "{}"
    )

    if source.source_type == "github":
        events = normalize_github(
            event_type=event_type,
            payload=payload,
            config=config,
        )
        if event_type == "push" and events:
            try:
                return enrich_github_push_events(
                    events=events,
                    payload=payload,
                    config=config,
                    provider_factory=github_provider_factory,
                )
            except Exception:
                # File evidence is optional enrichment. Never discard an
                # authenticated parent source event because provider evidence
                # is temporarily unavailable or malformed.
                return unavailable_github_push_events(
                    events=events,
                    payload=payload,
                    config=config,
                    reason="provider_enrichment_error",
                )
        return events

    if source.source_type == "gitlab":
        return normalize_gitlab(
            event_type=event_type,
            payload=payload,
            config=config,
        )

    if source.source_type == "jenkins":
        return normalize_jenkins(
            payload=payload,
            config=config,
        )

    if (
        source.source_type
        == "azure_devops"
    ):
        return normalize_azure_devops(
            payload=payload,
            config=config,
        )

    if (
        source.source_type
        == "terraform_cloud"
    ):
        return normalize_terraform_cloud(
            payload=payload,
            config=config,
        )

    return []


def _matches_filters(
    event,
    *,
    event_type: str,
    filters: dict[str, Any],
) -> bool:
    event_types = filters.get(
        "event_types"
    )

    if (
        isinstance(
            event_types,
            list,
        )
        and event_types
        and event_type.lower()
        not in {
            str(value).lower()
            for value
            in event_types
        }
    ):
        return False

    repositories = filters.get(
        "repositories"
    )

    if (
        isinstance(
            repositories,
            list,
        )
        and repositories
        and str(
            event.repository
            or ""
        ).lower()
        not in {
            str(value).lower()
            for value
            in repositories
        }
    ):
        return False

    environments = filters.get(
        "environments"
    )

    if (
        isinstance(
            environments,
            list,
        )
        and environments
        and str(
            event.environment
            or ""
        ).lower()
        not in {
            str(value).lower()
            for value
            in environments
        }
    ):
        return False

    return True


def _existing_delivery(
    session: Session,
    *,
    delivery_key: str,
) -> (
    ChangeSourceDeliveryRecord
    | None
):
    return session.scalar(
        select(
            ChangeSourceDeliveryRecord
        ).where(
            ChangeSourceDeliveryRecord
            .delivery_key
            == delivery_key
        )
    )


def _receipt(
    record: ChangeSourceDeliveryRecord,
    *,
    duplicate: bool,
) -> ChangeSourceDeliveryReceipt:
    try:
        event_ids = json.loads(
            record.event_ids_json
            or "[]"
        )

    except json.JSONDecodeError:
        event_ids = []

    return ChangeSourceDeliveryReceipt(
        delivery_id=record.delivery_id,
        source_id=record.source_id,
        event_type=record.event_type,
        status=record.status,
        duplicate=duplicate,
        event_ids=event_ids,
    )


def ingest_change_source_webhook(
    session: Session,
    *,
    source: ChangeSourceRecord,
    body: bytes,
    headers: dict[str, str],
    github_provider_factory: GitHubSourceEvidenceProviderFactory = (
        github_source_evidence_provider
    ),
) -> ChangeSourceDeliveryReceipt:
    if not source.enabled:
        raise ValueError(
            "Change source is disabled."
        )

    # Verify BEFORE parsing or storing.
    _verify(
        source=source,
        body=body,
        headers=headers,
    )

    try:
        payload = json.loads(
            body.decode("utf-8")
        )

    except Exception as exc:
        raise ValueError(
            "Webhook must contain "
            "valid JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Webhook payload must be "
            "a JSON object."
        )

    payload_hash = hashlib.sha256(
        body
    ).hexdigest()

    source_delivery_id = (
        _source_delivery_id(
            source_type=(
                source.source_type
            ),
            headers=headers,
            payload=payload,
            payload_hash=payload_hash,
        )
    )

    delivery_key = hashlib.sha256(
        (
            f"{source.source_id}|"
            f"{source_delivery_id}"
        ).encode("utf-8")
    ).hexdigest()

    existing = _existing_delivery(
        session,
        delivery_key=delivery_key,
    )

    if existing is not None:
        return _receipt(
            existing,
            duplicate=True,
        )

    event_type = _event_type(
        source_type=source.source_type,
        headers=headers,
        payload=payload,
    )

    now = utc_now_iso()

    delivery = (
        ChangeSourceDeliveryRecord(
            delivery_id=(
                "change-delivery:"
                + uuid4().hex
            ),
            source_id=source.source_id,
            delivery_key=delivery_key,
            source_delivery_id=(
                source_delivery_id
            ),
            event_type=event_type,
            status="received",
            payload_sha256=(
                payload_hash
            ),
            headers_json=json.dumps(
                _safe_headers(headers)
            ),
            payload_json=json.dumps(
                _redact(payload),
                default=str,
            ),
            event_ids_json="[]",
            received_at=now,
        )
    )

    session.add(delivery)

    source.delivery_count += 1
    source.last_event_at = now
    source.updated_at = now

    # Preserve authenticated delivery
    # even if normalization later fails.
    try:
        session.commit()

    except IntegrityError:
        session.rollback()

        existing = _existing_delivery(
            session,
            delivery_key=delivery_key,
        )

        if existing is not None:
            return _receipt(
                existing,
                duplicate=True,
            )

        raise

    try:
        events = _normalize(
            source=source,
            event_type=event_type,
            payload=payload,
            github_provider_factory=github_provider_factory,
        )

        filters = json.loads(
            source.filters_json
            or "{}"
        )

        events = [
            event
            for event in events
            if _matches_filters(
                event,
                event_type=event_type,
                filters=filters,
            )
        ]

        event_ids = []

        for event in events:
            receipt = ingest_change_event(
                session,
                request=event,
                auto_correlate=True,
                source_time_trusted=True,
                observed_at=delivery.received_at,
                commit=False,
            )

            event_ids.append(
                receipt.event_id
            )

        delivery = session.get(
            ChangeSourceDeliveryRecord,
            delivery.delivery_id,
        )

        source = session.get(
            ChangeSourceRecord,
            source.source_id,
        )

        if (
            delivery is None
            or source is None
        ):
            raise RuntimeError(
                "Change source delivery "
                "state disappeared."
            )

        delivery.status = (
            "accepted"
            if event_ids
            else "ignored"
        )

        delivery.event_ids_json = (
            json.dumps(event_ids)
        )

        delivery.processed_at = (
            utc_now_iso()
        )

        source.status = "healthy"

        source.last_success_at = (
            utc_now_iso()
        )

        source.last_error = None

        session.commit()

        return _receipt(
            delivery,
            duplicate=False,
        )

    except Exception as exc:
        session.rollback()

        delivery = session.get(
            ChangeSourceDeliveryRecord,
            delivery.delivery_id,
        )

        source = session.get(
            ChangeSourceRecord,
            source.source_id,
        )

        if (
            delivery is None
            or source is None
        ):
            raise

        error = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        delivery.status = (
            "dead_letter"
        )

        delivery.error = error

        delivery.processed_at = (
            utc_now_iso()
        )

        source.status = "error"

        source.failure_count += 1

        source.last_error = error

        source.last_error_at = (
            utc_now_iso()
        )

        dead_letter = (
            ChangeSourceDeadLetterRecord(
                dead_letter_id=(
                    "change-dead-letter:"
                    + uuid4().hex
                ),
                source_id=(
                    source.source_id
                ),
                delivery_id=(
                    delivery.delivery_id
                ),
                event_type=event_type,
                reason=error,
                payload_json=(
                    delivery.payload_json
                ),
                attempt_count=0,
                status="pending",
                created_at=(
                    utc_now_iso()
                ),
            )
        )

        session.add(dead_letter)

        session.commit()

        raise


def replay_dead_letter(
    session: Session,
    *,
    dead_letter_id: str,
) -> ChangeSourceReplayResponse:
    dead_letter = session.get(
        ChangeSourceDeadLetterRecord,
        dead_letter_id,
    )

    if dead_letter is None:
        raise ValueError(
            "Dead letter not found."
        )

    source = session.get(
        ChangeSourceRecord,
        dead_letter.source_id,
    )

    delivery = session.get(
        ChangeSourceDeliveryRecord,
        dead_letter.delivery_id,
    )

    if (
        source is None
        or delivery is None
    ):
        raise ValueError(
            "Dead-letter source or "
            "delivery no longer exists."
        )

    dead_letter.attempt_count += 1

    dead_letter.last_attempt_at = (
        utc_now_iso()
    )

    try:
        payload = json.loads(
            dead_letter.payload_json
        )

        events = _normalize(
            source=source,
            event_type=(
                dead_letter.event_type
                or "unknown"
            ),
            payload=payload,
        )

        filters = json.loads(
            source.filters_json
            or "{}"
        )

        events = [
            event
            for event in events
            if _matches_filters(
                event,
                event_type=(
                    dead_letter.event_type
                    or "unknown"
                ),
                filters=filters,
            )
        ]

        event_ids = []

        for event in events:
            receipt = ingest_change_event(
                session,
                request=event,
                auto_correlate=True,
                source_time_trusted=True,
                # Replay preserves the first authenticated delivery time;
                # replay processing time remains in delivery.processed_at.
                observed_at=delivery.received_at,
                commit=False,
            )

            event_ids.append(
                receipt.event_id
            )

        dead_letter.status = "replayed"

        dead_letter.replayed_at = (
            utc_now_iso()
        )

        delivery.status = (
            "accepted"
            if event_ids
            else "ignored"
        )

        delivery.event_ids_json = (
            json.dumps(event_ids)
        )

        delivery.error = None

        delivery.processed_at = (
            utc_now_iso()
        )

        source.status = "healthy"

        source.last_success_at = (
            utc_now_iso()
        )

        source.last_error = None

        session.commit()

        return (
            ChangeSourceReplayResponse(
                dead_letter_id=(
                    dead_letter_id
                ),
                succeeded=True,
                event_ids=event_ids,
            )
        )

    except Exception as exc:
        session.rollback()

        dead_letter = session.get(
            ChangeSourceDeadLetterRecord,
            dead_letter_id,
        )

        if dead_letter is not None:
            dead_letter.status = (
                "pending"
            )

            dead_letter.reason = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            dead_letter.last_attempt_at = (
                utc_now_iso()
            )

            session.commit()

        return (
            ChangeSourceReplayResponse(
                dead_letter_id=(
                    dead_letter_id
                ),
                succeeded=False,
                event_ids=[],
                error=str(exc),
            )
        )
