from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CloudAccountRecord,
    CloudResourceRecord,
    SnapshotRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import (
    AgentSnapshotSubmission,
)
from app.models.clouds import (
    AgentCloudStatusResponse,
    CloudAccountView,
    CloudResourceView,
    CloudTopologyResponse,
)
from app.models.topology import (
    GraphSnapshot,
)


def _cloud_resource_id(
    *,
    provider: str,
    account_id: str,
    region: str,
    resource_type: str,
    resource_id: str,
) -> str:
    identity = "|".join(
        [
            provider,
            account_id,
            region,
            resource_type,
            resource_id,
        ]
    )

    digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:40]

    return (
        f"cloud-resource:{provider}:"
        f"{digest}"
    )


def persist_cloud_inventory(
    session: Session,
    *,
    agent: TopoAgentRecord,
    submission:
        AgentSnapshotSubmission,
) -> None:
    inventory = submission.inventory

    account_values = inventory.get(
        "aws_accounts",
        [],
    )

    for value in account_values:
        if not isinstance(value, dict):
            continue

        account_id = str(
            value.get(
                "account_id"
            )
            or value.get(
                "resource_id"
            )
            or ""
        )

        if not account_id:
            continue

        properties = value.get(
            "properties",
            {},
        )

        if not isinstance(
            properties,
            dict,
        ):
            properties = {}

        record_id = (
            f"aws:{account_id}"
        )

        record = session.get(
            CloudAccountRecord,
            record_id,
        )

        now = utc_now_iso()

        if record is None:
            record = CloudAccountRecord(
                cloud_account_id=(
                    record_id
                ),
                provider="aws",
                account_number=(
                    account_id
                ),
                display_name=str(
                    value.get("name")
                    or account_id
                ),
                principal_arn=(
                    properties.get(
                        "principal_arn"
                    )
                ),
                metadata_json=json.dumps(
                    properties
                ),
                last_seen_at=(
                    submission
                    .collected_at
                ),
                created_at=now,
                updated_at=now,
            )

            session.add(record)

        else:
            record.display_name = str(
                value.get("name")
                or account_id
            )

            record.principal_arn = (
                properties.get(
                    "principal_arn"
                )
            )

            record.metadata_json = (
                json.dumps(properties)
            )

            record.last_seen_at = (
                submission.collected_at
            )

            record.updated_at = now

    for values in inventory.values():
        if not isinstance(values, list):
            continue

        for value in values:
            if not isinstance(
                value,
                dict,
            ):
                continue

            provider = str(
                value.get(
                    "provider",
                    "",
                )
            )

            resource_type = str(
                value.get(
                    "resource_type",
                    "",
                )
            )

            if (
                provider != "aws"
                or resource_type
                == "aws_account"
            ):
                continue

            account_id = str(
                value.get(
                    "account_id",
                    "",
                )
            )

            region = str(
                value.get(
                    "region",
                    "global",
                )
            )

            resource_id = str(
                value.get(
                    "resource_id",
                    "",
                )
            )

            if (
                not account_id
                or not resource_type
                or not resource_id
            ):
                continue

            record_id = (
                _cloud_resource_id(
                    provider=provider,
                    account_id=account_id,
                    region=region,
                    resource_type=(
                        resource_type
                    ),
                    resource_id=(
                        resource_id
                    ),
                )
            )

            record = session.get(
                CloudResourceRecord,
                record_id,
            )

            now = utc_now_iso()

            fields = {
                "provider": provider,
                "account_id":
                    account_id,
                "region": region,
                "resource_type":
                    resource_type,
                "resource_id":
                    resource_id,
                "arn": value.get("arn"),
                "name": str(
                    value.get("name")
                    or resource_id
                ),
                "status":
                    value.get("status"),
                "vpc_id":
                    value.get("vpc_id"),
                "subnet_ids_json":
                    json.dumps(
                        value.get(
                            "subnet_ids",
                            [],
                        )
                    ),
                "tags_json":
                    json.dumps(
                        value.get(
                            "tags",
                            {},
                        )
                    ),
                "properties_json":
                    json.dumps(
                        value.get(
                            "properties",
                            {},
                        )
                    ),
                "observed_at":
                    submission
                    .collected_at,
                "agent_id":
                    agent.agent_id,
                "updated_at": now,
            }

            if record is None:
                record = CloudResourceRecord(
                    cloud_resource_id=(
                        record_id
                    ),
                    created_at=now,
                    **fields,
                )

                session.add(record)

            else:
                for (
                    field_name,
                    field_value,
                ) in fields.items():
                    setattr(
                        record,
                        field_name,
                        field_value,
                    )

    session.commit()


def _account_view(
    record: CloudAccountRecord,
) -> CloudAccountView:
    return CloudAccountView(
        cloud_account_id=(
            record.cloud_account_id
        ),
        provider=record.provider,
        account_number=(
            record.account_number
        ),
        display_name=(
            record.display_name
        ),
        principal_arn=(
            record.principal_arn
        ),
        metadata=json.loads(
            record.metadata_json
        ),
        last_seen_at=(
            record.last_seen_at
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def list_cloud_accounts(
    session: Session,
    *,
    provider: str | None = None,
) -> list[CloudAccountView]:
    statement = select(
        CloudAccountRecord
    )

    if provider:
        statement = statement.where(
            CloudAccountRecord.provider
            == provider
        )

    statement = statement.order_by(
        CloudAccountRecord
        .display_name
        .asc()
    )

    return [
        _account_view(record)
        for record in session.scalars(
            statement
        ).all()
    ]


def _resource_view(
    record: CloudResourceRecord,
) -> CloudResourceView:
    return CloudResourceView(
        cloud_resource_id=(
            record.cloud_resource_id
        ),
        provider=record.provider,
        account_id=(
            record.account_id
        ),
        region=record.region,
        resource_type=(
            record.resource_type
        ),
        resource_id=(
            record.resource_id
        ),
        arn=record.arn,
        name=record.name,
        status=record.status,
        vpc_id=record.vpc_id,
        subnet_ids=json.loads(
            record.subnet_ids_json
        ),
        tags=json.loads(
            record.tags_json
        ),
        properties=json.loads(
            record.properties_json
        ),
        observed_at=(
            record.observed_at
        ),
        agent_id=record.agent_id,
    )


def list_cloud_resources(
    session: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    region: str | None = None,
    resource_type: str | None = None,
    tag_key: str | None = None,
    tag_value: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[CloudResourceView]:
    statement = select(
        CloudResourceRecord
    )

    if provider:
        statement = statement.where(
            CloudResourceRecord.provider
            == provider
        )

    if account_id:
        statement = statement.where(
            CloudResourceRecord.account_id
            == account_id
        )

    if region:
        statement = statement.where(
            CloudResourceRecord.region
            == region
        )

    if resource_type:
        statement = statement.where(
            CloudResourceRecord
            .resource_type
            == resource_type
        )

    statement = (
        statement
        .order_by(
            CloudResourceRecord
            .observed_at
            .desc()
        )
        .offset(offset)
        .limit(limit)
    )

    values = [
        _resource_view(record)
        for record in session.scalars(
            statement
        ).all()
    ]

    if tag_key:
        values = [
            item
            for item in values
            if tag_key in item.tags
            and (
                tag_value is None
                or item.tags.get(
                    tag_key
                )
                == tag_value
            )
        ]

    return values


def latest_cloud_topology(
    session: Session,
    *,
    provider: str = "aws",
    account_id: str | None = None,
    region: str | None = None,
) -> CloudTopologyResponse:
    statement = (
        select(SnapshotRecord)
        .order_by(
            SnapshotRecord
            .created_at
            .desc()
        )
        .limit(100)
    )

    for record in session.scalars(
        statement
    ).all():
        try:
            snapshot = (
                GraphSnapshot
                .model_validate_json(
                    record.payload_json
                )
            )

        except Exception:
            continue

        cloud_entities = [
            entity
            for entity in snapshot.entities
            if (
                entity.source_system
                == provider
                and (
                    account_id is None
                    or str(
                        entity.properties.get(
                            "account_id",
                            "",
                        )
                    )
                    == account_id
                )
                and (
                    region is None
                    or str(
                        entity.properties.get(
                            "region",
                            "",
                        )
                    )
                    == region
                )
            )
        ]

        if not cloud_entities:
            continue

        selected_ids = {
            entity.id
            for entity in cloud_entities
        }

        selected_relationships = [
            relationship
            for relationship
            in snapshot.relationships
            if (
                relationship
                .source_entity_id
                in selected_ids
                or relationship
                .target_entity_id
                in selected_ids
            )
        ]

        neighboring_ids = {
            relationship
            .source_entity_id
            for relationship
            in selected_relationships
        } | {
            relationship
            .target_entity_id
            for relationship
            in selected_relationships
        }

        selected_entities = [
            entity
            for entity in snapshot.entities
            if entity.id in (
                selected_ids
                | neighboring_ids
            )
        ]

        return CloudTopologyResponse(
            snapshot_id=(
                snapshot.snapshot_id
            ),
            provider=provider,
            account_id=account_id,
            region=region,
            entities=selected_entities,
            relationships=(
                selected_relationships
            ),
        )

    return CloudTopologyResponse(
        snapshot_id=None,
        provider=provider,
        account_id=account_id,
        region=region,
        entities=[],
        relationships=[],
    )


def agent_cloud_status(
    session: Session,
    *,
    agent_id: str,
) -> AgentCloudStatusResponse | None:
    record = session.get(
        TopoAgentRecord,
        agent_id,
    )

    if record is None:
        return None

    metadata = json.loads(
        record.metadata_json
    )

    raw_plugins = metadata.get(
        "plugins",
        [],
    )

    aws_status: dict[
        str,
        Any,
    ] | None = None

    if isinstance(
        raw_plugins,
        list,
    ):
        aws_status = next(
            (
                item
                for item in raw_plugins
                if isinstance(
                    item,
                    dict,
                )
                and item.get("name")
                == "aws"
            ),
            None,
        )

    if aws_status is None:
        return AgentCloudStatusResponse(
            agent_id=agent_id,
            enabled=False,
            provider="aws",
            status="not_enabled",
            account_id=None,
            regions=[],
            resource_count=0,
            errors=[],
            last_heartbeat_at=(
                record.last_heartbeat_at
            ),
            updated_at=(
                record.updated_at
            ),
        )

    return AgentCloudStatusResponse(
        agent_id=agent_id,
        enabled=True,
        provider="aws",
        status=str(
            aws_status.get(
                "status",
                "unknown",
            )
        ),
        account_id=(
            aws_status.get(
                "account_id"
            )
        ),
        regions=[
            str(item)
            for item in aws_status.get(
                "regions",
                [],
            )
        ],
        resource_count=int(
            aws_status.get(
                "resource_count",
                0,
            )
        ),
        errors=[
            str(item)
            for item in aws_status.get(
                "errors",
                [],
            )
        ],
        last_heartbeat_at=(
            record.last_heartbeat_at
        ),
        updated_at=record.updated_at,
    )