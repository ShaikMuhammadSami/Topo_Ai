from __future__ import annotations
from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)

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
    submission: AgentSnapshotSubmission,
    tenant_id: DomainTenant,
) -> None:
    inventory = submission.inventory

    account_resource_types = {
        "aws_account",
        "azure_subscription",
        "gcp_project",
    }

    now = utc_now_iso()

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
            ).lower()

            resource_type = str(
                value.get(
                    "resource_type",
                    "",
                )
            )

            account_id = str(
                value.get(
                    "account_id",
                    "",
                )
            )

            if (
                provider
                not in {
                    "aws",
                    "azure",
                    "gcp",
                }
                or not account_id
            ):
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

            if resource_type in account_resource_types:
                record_id = (
                    f"{provider}:"
                    f"{account_id}"
                )

                record = tenant_get(
                    session,
                    CloudAccountRecord,
                    record_id,
                    tenant_id=tenant_id,
                )

                metadata = {
                    **properties,
                    "status":
                        value.get(
                            "status"
                        ),
                    "provider_resource_id":
                        value.get(
                            "resource_id"
                        ),
                }

                principal = (
                    properties.get(
                        "principal_arn"
                    )
                    or properties.get(
                        "principal_id"
                    )
                )

                if record is None:
                    record = CloudAccountRecord(
                        cloud_account_id=(record_id),
                        provider=provider,
                        account_number=(account_id),
                        display_name=str(value.get("name") or account_id),
                        principal_arn=(str(principal) if principal else None),
                        metadata_json=(json.dumps(metadata)),
                        last_seen_at=(submission.collected_at),
                        created_at=now,
                        updated_at=now,
                        tenant_id=tenant_value(tenant_id),
                    )

                    session.add(record)

                else:
                    record.display_name = (
                        str(
                            value.get(
                                "name"
                            )
                            or account_id
                        )
                    )

                    record.principal_arn = (
                        str(principal)
                        if principal
                        else None
                    )

                    record.metadata_json = (
                        json.dumps(metadata)
                    )

                    record.last_seen_at = (
                        submission
                        .collected_at
                    )

                    record.updated_at = now

                continue

            resource_id = str(
                value.get(
                    "resource_id",
                    "",
                )
            )

            region = str(
                value.get(
                    "region",
                    "global",
                )
            )

            if (
                not resource_type
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

            record = tenant_get(
                session,
                CloudResourceRecord,
                record_id,
                tenant_id=tenant_id,
            )

            raw_properties = value.get(
                "properties",
                {},
            )

            if not isinstance(
                raw_properties,
                dict,
            ):
                raw_properties = {}

            resource_group = value.get(
                "resource_group"
            )

            enriched_properties = {
                **raw_properties,
                "resource_group":
                    resource_group,
            }

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
                        enriched_properties
                    ),
                "observed_at":
                    submission.collected_at,
                "agent_id":
                    agent.agent_id,
                "updated_at": now,
            }

            if record is None:
                record = CloudResourceRecord(
                    cloud_resource_id=(record_id),
                    created_at=now,
                    **fields,
                    tenant_id=tenant_value(tenant_id),
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

    tenant_commit(session, tenant_id=tenant_id)


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
    tenant_id: DomainTenant,
) -> list[CloudAccountView]:
    statement = select(CloudAccountRecord).where(
        tenant_predicate(CloudAccountRecord, tenant_id)
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
    tenant_id: DomainTenant,
) -> list[CloudResourceView]:
    statement = select(CloudResourceRecord).where(
        tenant_predicate(CloudResourceRecord, tenant_id)
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
    tenant_id: DomainTenant,
) -> CloudTopologyResponse:
    statement = (
        select(SnapshotRecord)
        .where(tenant_predicate(SnapshotRecord, tenant_id))
        .order_by(SnapshotRecord.created_at.desc())
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
    provider: str = "aws",
) -> AgentCloudStatusResponse | None:
    record = session.get(
        TopoAgentRecord,
        agent_id,
    )

    if record is None:
        return None

    provider = provider.lower()

    metadata = json.loads(
        record.metadata_json
    )

    raw_plugins = metadata.get(
        "plugins",
        [],
    )

    plugin_status: dict[
        str,
        Any,
    ] | None = None

    if isinstance(
        raw_plugins,
        list,
    ):
        plugin_status = next(
            (
                item
                for item in raw_plugins
                if isinstance(
                    item,
                    dict,
                )
                and str(
                    item.get("name")
                    or ""
                ).lower()
                == provider
            ),
            None,
        )

    if plugin_status is None:
        return AgentCloudStatusResponse(
            agent_id=agent_id,
            enabled=False,
            provider=provider,
            status="not_enabled",
            account_id=None,
            account_ids=[],
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

    if provider == "azure":
        account_ids = [
            str(item)
            for item in plugin_status.get(
                "subscription_ids",
                [],
            )
        ]

        regions = [
            str(item)
            for item in plugin_status.get(
                "locations",
                [],
            )
        ]
    
    elif provider == "gcp":
        account_ids = [
            str(item)
            for item in plugin_status.get(
                "project_ids",
                plugin_status.get(
                    "account_ids",
                    [],
                )
            )
        ]

        regions = [
            str(item)
            for item in plugin_status.get(
                "locations",
                [],
            )
        ]

    else:
        account_value = (
            plugin_status.get(
                "account_id"
            )
        )

        account_ids = (
            [str(account_value)]
            if account_value
            else []
        )

        regions = [
            str(item)
            for item in plugin_status.get(
                "regions",
                [],
            )
        ]

    account_id = (
        account_ids[0]
        if len(account_ids) == 1
        else None
    )

    return AgentCloudStatusResponse(
        agent_id=agent_id,
        enabled=True,
        provider=provider,
        status=str(
            plugin_status.get(
                "status",
                "unknown",
            )
        ),
        account_id=account_id,
        account_ids=account_ids,
        regions=regions,
        resource_count=int(
            plugin_status.get(
                "resource_count",
                0,
            )
        ),
        errors=[
            str(item)
            for item in plugin_status.get(
                "errors",
                [],
            )
        ],
        last_heartbeat_at=(
            record.last_heartbeat_at
        ),
        updated_at=record.updated_at,
    )
