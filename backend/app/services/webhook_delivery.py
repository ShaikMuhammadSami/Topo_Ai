from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_value,
    require_record_owner,
)

import hashlib
import hmac
import json
import time
from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

import httpcore
import httpx
from sqlalchemy.orm import Session

from app.db.models import (
    WebhookDeliveryRecord,
    WebhookEndpointRecord,
    utc_now_iso,
)
from app.models.webhooks import (
    WebhookDeliveryStatus,
    WebhookDeliveryView,
    WebhookEvent,
    WebhookEventPayload,
    WebhookEventType,
    WebhookTestPayload,
    WEBHOOK_PAYLOAD_TYPE_BY_EVENT,
)
from app.repositories.webhook_repository import (
    find_delivery_record,
    list_webhook_endpoint_records,
    save_delivery_result,
)
from app.services.secret_consumers import SecretConsumerError, load_webhook_secrets
from app.services.secret_runtime import runtime_secret_store
from app.models.secret_store import SecretStoreError
from app.services.secret_store import SecretStore
from app.security.egress_policy import (
    EgressPolicyError,
    EgressPurpose,
    Resolver,
    SystemResolver,
    prepare_destination,
)
from app.services.egress_http import deliver_webhook_once
from app.security.customer_data_policy import (
    CONTROL,
    STRUCTURED,
    TENANT_META,
    USER_TEXT,
    ExternalDataSink,
    require_content_classes,
)


MAX_WEBHOOK_BODY_BYTES = 131_072
_WEBHOOK_CONTENT_CLASSES = frozenset(
    {CONTROL, TENANT_META, STRUCTURED, USER_TEXT}
)


def build_webhook_event(
    event_type: WebhookEventType,
    resource_type: str,
    resource_id: str,
    summary: str,
    payload: WebhookEventPayload,
    severity: str | None = None,
    dedupe_key: str | None = None,
) -> WebhookEvent:
    expected_payload = WEBHOOK_PAYLOAD_TYPE_BY_EVENT[event_type]
    if not isinstance(payload, expected_payload):
        raise ValueError("webhook_payload_type_invalid")
    effective_key = (
        dedupe_key
        or resource_id
    )

    value = "|".join(
        [
            event_type.value,
            effective_key,
        ]
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return WebhookEvent(
        event_id=f"event:{digest}",
        event_type=event_type,
        occurred_at=datetime.now(
            timezone.utc
        ),
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        severity=severity,
        payload=payload,
    )


def _event_body(
    event: WebhookEvent,
) -> str:
    require_content_classes(
        ExternalDataSink.TENANT_WEBHOOK,
        _WEBHOOK_CONTENT_CLASSES,
    )
    body = json.dumps(
        event.model_dump(
            mode="json"
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(body.encode("utf-8")) > MAX_WEBHOOK_BODY_BYTES:
        raise ValueError("webhook_body_too_large")
    return body


def _subscribed(
    endpoint: WebhookEndpointRecord,
    event: WebhookEvent,
) -> bool:
    values = json.loads(
        endpoint.event_types_json
    )

    return (
        event.event_type.value
        in values
    )


def _signature(
    secret: str,
    body: str,
) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"sha256={digest}"


def deliver_event_to_endpoint(
    session: Session,
    endpoint: WebhookEndpointRecord,
    event: WebhookEvent,
    *,
    tenant_id: DomainTenant,
    secret_store: SecretStore | None = None,
    resolver: Resolver | None = None,
    network_backend: httpcore.NetworkBackend | None = None,
) -> WebhookDeliveryView:
    require_record_owner(endpoint, tenant_id=tenant_id)
    body = _event_body(event)

    requested_at = utc_now_iso()

    headers = {
        "Content-Type":
            "application/json",
        "User-Agent":
            "Topo-AI-Webhook/0.1",
        "X-Topo-Event":
            event.event_type.value,
        "X-Topo-Event-Id":
            event.event_id,
        "X-Topo-Timestamp":
            event.occurred_at.isoformat(),
    }

    response_status = None
    response_body = None
    error_message = None

    delivery_status = (
        WebhookDeliveryStatus.FAILED
    )

    attempt_count = 0

    destination_resolver = resolver or SystemResolver()
    credentials_loaded = False
    credential_error = None

    for attempt in range(
        1,
        endpoint.max_attempts + 1,
    ):
        attempt_count = attempt

        try:
            destination = prepare_destination(
                endpoint.url,
                purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
                resolver=destination_resolver,
            )
            if not credentials_loaded:
                try:
                    store = secret_store or runtime_secret_store()
                    signing_secret, protected_headers, _ = load_webhook_secrets(
                        session, endpoint=endpoint, tenant_id=tenant_id, store=store
                    )
                except (SecretConsumerError, SecretStoreError):
                    credential_error = "Webhook credential service is unavailable."
                    attempt_count = 0
                    break
                headers.update(protected_headers)
                if signing_secret:
                    headers["X-Topo-Signature"] = _signature(signing_secret, body)
                credentials_loaded = True

            response_status = deliver_webhook_once(
                destination,
                body=body,
                headers=headers,
                resolver=destination_resolver,
                network_backend=network_backend,
                timeout_seconds=endpoint.timeout_seconds,
            )

            # Remote bodies are untrusted and may echo request credentials.
            # Status is retained; arbitrary remote text is never persisted.
            response_body = None

            if (
                200
                <= response_status
                < 300
            ):
                delivery_status = (
                    WebhookDeliveryStatus
                    .SUCCEEDED
                )

                error_message = None
                break

            error_message = (
                "Webhook returned HTTP "
                f"{response_status}."
            )

            if 300 <= response_status < 400:
                break

        except EgressPolicyError as exc:
            error_message = f"Webhook transport failed ({exc.code.value})."
        except httpx.TimeoutException:
            error_message = "Webhook transport failed (timeout)."
        except httpx.RequestError:
            error_message = "Webhook transport failed (upstream_unavailable)."
        except Exception:
            error_message = "Webhook transport failed (upstream_unavailable)."

        if attempt < endpoint.max_attempts:
            time.sleep(
                min(
                    0.25
                    * (2 ** (attempt - 1)),
                    2.0,
                )
            )

    if credential_error is not None:
        error_message = credential_error
    completed_at = utc_now_iso()

    delivery_id_value = "|".join(
        [
            endpoint.webhook_id,
            event.event_id,
        ]
    )

    delivery_digest = hashlib.sha256(
        delivery_id_value.encode(
            "utf-8"
        )
    ).hexdigest()[:32]

    record = WebhookDeliveryRecord(
        delivery_id=(f"delivery:" f"{delivery_digest}"),
        webhook_id=endpoint.webhook_id,
        event_id=event.event_id,
        event_type=(event.event_type.value),
        resource_type=(event.resource_type),
        resource_id=event.resource_id,
        status=delivery_status.value,
        attempt_count=attempt_count,
        response_status=response_status,
        response_body=response_body,
        error_message=error_message,
        requested_at=requested_at,
        completed_at=completed_at,
        payload_json=body,
        created_at=requested_at,
        updated_at=completed_at,
        tenant_id=tenant_value(tenant_id),
    )

    return save_delivery_result(
        session=session,
        record=record,
        tenant_id=tenant_id,
    )


def publish_event(
    session: Session,
    event: WebhookEvent,
    *,
    tenant_id: DomainTenant,
    secret_store: SecretStore | None = None,
    resolver: Resolver | None = None,
    network_backend: httpcore.NetworkBackend | None = None,
) -> list[WebhookDeliveryView]:
    deliveries: list[
        WebhookDeliveryView
    ] = []

    endpoints = list_webhook_endpoint_records(
        session=session,
        active=True,
        tenant_id=tenant_id,
    )

    for endpoint in endpoints:
        if not _subscribed(
            endpoint,
            event,
        ):
            continue

        existing = find_delivery_record(
            session=session,
            webhook_id=(endpoint.webhook_id),
            event_id=event.event_id,
            tenant_id=tenant_id,
        )

        if (
            existing
            and existing.status
            == WebhookDeliveryStatus
            .SUCCEEDED.value
        ):
            continue

        delivery = deliver_event_to_endpoint(
            session=session,
            endpoint=endpoint,
            event=event,
            tenant_id=tenant_id,
            secret_store=secret_store,
            resolver=resolver,
            network_backend=network_backend,
        )

        deliveries.append(delivery)

    return deliveries


def publish_event_safely(
    session: Session,
    event: WebhookEvent,
    *,
    tenant_id: DomainTenant,
    secret_store: SecretStore | None = None,
    resolver: Resolver | None = None,
    network_backend: httpcore.NetworkBackend | None = None,
) -> list[str]:
    try:
        deliveries = publish_event(
            session=session,
            event=event,
            tenant_id=tenant_id,
            secret_store=secret_store,
            resolver=resolver,
            network_backend=network_backend,
        )

        return [
            (
                f"Webhook delivery failed: "
                f"{delivery.webhook_name or delivery.webhook_id}"
            )
            for delivery in deliveries
            if delivery.status
            == WebhookDeliveryStatus.FAILED
        ]

    except Exception as exc:
        session.rollback()

        return [f"Webhook publication failed ({type(exc).__name__})."]


def create_test_event(
    webhook_id: str,
    summary: str,
) -> WebhookEvent:
    return build_webhook_event(
        event_type=(
            WebhookEventType.TEST
        ),
        resource_type="webhook",
        resource_id=webhook_id,
        summary=summary,
        payload=WebhookTestPayload(webhook_id=webhook_id),
        severity="info",
        dedupe_key=(
            f"{webhook_id}:"
            f"{uuid4().hex}"
        ),
    )
