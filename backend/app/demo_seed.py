"""Create a synthetic local-only workspace, topology change, and incident."""

from __future__ import annotations

from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.db.database import DATABASE_URL, SessionLocal, init_db
from app.db.models import IncidentRecord
from app.models.lifecycle_automation import TopologyCheckpointReason
from app.models.topology import GraphSnapshot
from app.repositories.signal_repository import load_signal
from app.repositories.snapshot_repository import load_snapshot
from app.repositories.tenant_repository import list_active_tenants_for_principal
from app.security.api_tokens import development_principal
from app.security.auth_config import AuthMode, load_auth_configuration
from app.security.authorization_enforcement import (
    authorize_tenant,
    bind_authorization_context,
    reset_authorization_context,
)
from app.security.authorization_policy import Permission, TenantRole
from app.security.tenant_context import resolve_tenant_context
from app.services.continuous_lifecycle import (
    failure_signals_from_snapshot,
    ingest_failure_signal_batch,
)
from app.services.incident_grouping import incident_fingerprint
from app.services.sample_topology import build_sample_snapshot
from app.services.tenant_service import create_tenant_with_creator_membership
from app.services.topology_checkpoint import persist_topology_checkpoint


DEMO_TENANT_NAME = "Topo AI Local Demo"
BASELINE_SNAPSHOT_ID = "snapshot:demo-cluster:local-demo-baseline-v1"
DEPLOYMENT_CHANGE_SNAPSHOT_ID = (
    "snapshot:demo-cluster:local-demo-deployment-change-v1"
)
FAILURE_SNAPSHOT_ID = "snapshot:demo-cluster:local-demo-failure-v1"
PAYMENT_DEPLOYMENT_ID = (
    "k8s:demo-cluster:deployment:payments:payment-service"
)
PAYMENT_POD_ID = "k8s:demo-cluster:pod:payments:payment-service-7c9f8"
DEMO_SNAPSHOT_INTERVAL = timedelta(minutes=1)


def _demo_tenant_id(session, principal) -> str:
    if not principal.principal_id:
        raise RuntimeError("The local development principal is unavailable.")

    for tenant, membership in list_active_tenants_for_principal(
        session,
        principal_id=principal.principal_id,
    ):
        if tenant.display_name == DEMO_TENANT_NAME:
            if membership.role != TenantRole.ADMIN.value:
                raise RuntimeError(
                    "The existing local demo tenant membership is not an admin."
                )
            return tenant.tenant_id

    created = create_tenant_with_creator_membership(
        session,
        display_name=DEMO_TENANT_NAME,
        creator_subject=principal.subject,
        creator_principal_id=principal.principal_id,
    )
    return created.tenant_id


def _retime_snapshot(snapshot: GraphSnapshot, collected_at) -> GraphSnapshot:
    return snapshot.model_copy(
        update={
            "collected_at": collected_at,
            "entities": [
                entity.model_copy(update={"observed_at": collected_at})
                for entity in snapshot.entities
            ],
            "relationships": [
                relationship.model_copy(update={"observed_at": collected_at})
                for relationship in snapshot.relationships
            ],
            "evidence": [
                evidence.model_copy(update={"observed_at": collected_at})
                for evidence in snapshot.evidence
            ],
        }
    )


def _deployment_change_snapshot(baseline: GraphSnapshot) -> GraphSnapshot:
    snapshot = _retime_snapshot(
        baseline,
        baseline.collected_at + DEMO_SNAPSHOT_INTERVAL,
    )

    entities = []
    for entity in snapshot.entities:
        if entity.id == PAYMENT_DEPLOYMENT_ID:
            properties = dict(entity.properties)
            properties["containers"] = [
                {
                    "name": "payment-service",
                    "image": "payment-service:v2",
                }
            ]
            entity = entity.model_copy(update={"properties": properties})
        entities.append(entity)

    if not any(entity.id == PAYMENT_DEPLOYMENT_ID for entity in entities):
        raise RuntimeError(
            "The built-in sample topology no longer contains the payment deployment."
        )

    return snapshot.model_copy(
        update={
            "snapshot_id": DEPLOYMENT_CHANGE_SNAPSHOT_ID,
            "entities": entities,
        }
    )


def _failure_snapshot(deployment_change: GraphSnapshot) -> GraphSnapshot:
    snapshot = _retime_snapshot(
        deployment_change,
        deployment_change.collected_at + DEMO_SNAPSHOT_INTERVAL,
    )

    entities = []
    for entity in snapshot.entities:
        if entity.id == PAYMENT_POD_ID:
            properties = dict(entity.properties)
            properties["container_statuses"] = [
                {"waiting_reason": "CrashLoopBackOff"}
            ]
            entity = entity.model_copy(update={"properties": properties})
        entities.append(entity)

    if not any(entity.id == PAYMENT_POD_ID for entity in entities):
        raise RuntimeError(
            "The built-in sample topology no longer contains the payment pod."
        )

    return snapshot.model_copy(
        update={
            "snapshot_id": FAILURE_SNAPSHOT_ID,
            "entities": entities,
        }
    )


def main() -> None:
    configuration = load_auth_configuration(database_url=DATABASE_URL)
    if configuration.mode is not AuthMode.DEVELOPMENT_DISABLED:
        raise SystemExit(
            "Demo seeding requires TOPO_AUTH_MODE=development-disabled."
        )
    if make_url(DATABASE_URL).get_backend_name() != "sqlite":
        raise SystemExit("Demo seeding is restricted to SQLite.")

    init_db()

    with SessionLocal() as session:
        principal = development_principal(session)
        tenant_id = _demo_tenant_id(session, principal)
        tenant_context = resolve_tenant_context(
            session,
            principal=principal,
            selected_tenant_id=tenant_id,
            credential_id=None,
        )
        authorization_context = authorize_tenant(
            session,
            principal=principal,
            tenant_context=tenant_context,
            required_permissions=frozenset(
                {
                    Permission.INTEGRATION_MANAGE,
                    Permission.INCIDENT_RESPOND,
                }
            ),
        )
        context_token = bind_authorization_context(authorization_context)

        try:
            baseline_candidate = build_sample_snapshot().model_copy(
                update={"snapshot_id": BASELINE_SNAPSHOT_ID}
            )
            persist_topology_checkpoint(
                session,
                snapshot=baseline_candidate,
                reason=TopologyCheckpointReason.MANUAL,
                derive_changes=False,
                force=True,
                tenant_id=tenant_id,
                authorization_context=authorization_context,
            )
            baseline = load_snapshot(
                session,
                BASELINE_SNAPSHOT_ID,
                tenant_id=tenant_id,
            )
            if baseline is None:
                raise RuntimeError("The local baseline snapshot was not saved.")

            deployment_checkpoint = persist_topology_checkpoint(
                session,
                snapshot=_deployment_change_snapshot(baseline),
                reason=TopologyCheckpointReason.MANUAL,
                derive_changes=True,
                force=True,
                tenant_id=tenant_id,
                authorization_context=authorization_context,
            )
            deployment_change = load_snapshot(
                session,
                DEPLOYMENT_CHANGE_SNAPSHOT_ID,
                tenant_id=tenant_id,
            )
            if deployment_change is None:
                raise RuntimeError(
                    "The local deployment-change snapshot was not saved."
                )

            failure_checkpoint = persist_topology_checkpoint(
                session,
                snapshot=_failure_snapshot(deployment_change),
                reason=TopologyCheckpointReason.MANUAL,
                derive_changes=True,
                force=True,
                tenant_id=tenant_id,
                authorization_context=authorization_context,
            )
            failure = load_snapshot(
                session,
                FAILURE_SNAPSHOT_ID,
                tenant_id=tenant_id,
            )
            if failure is None:
                raise RuntimeError("The local failure snapshot was not saved.")

            signals = failure_signals_from_snapshot(failure)
            if not signals:
                raise RuntimeError(
                    "The synthetic failure state did not produce a failure signal."
                )

            fingerprints = {incident_fingerprint(signal) for signal in signals}
            existing_incidents = set(
                session.scalars(
                    select(IncidentRecord.fingerprint).where(
                        IncidentRecord.tenant_id == tenant_id,
                        IncidentRecord.fingerprint.in_(fingerprints),
                    )
                ).all()
            )
            signals_to_ingest = [
                signal
                for signal in signals
                if (
                    incident_fingerprint(signal) not in existing_incidents
                    or load_signal(
                        session,
                        signal.signal_id,
                        tenant_id=tenant_id,
                    ) is None
                )
            ]

            batch = None
            if signals_to_ingest:
                batch = ingest_failure_signal_batch(
                    session,
                    signals=signals_to_ingest,
                    tenant_id=tenant_id,
                    authorization_context=authorization_context,
                )

            print(f"Workspace: {DEMO_TENANT_NAME}")
            print(f"Tenant ID: {tenant_id}")
            print(f"Baseline snapshot: {baseline.snapshot_id}")
            print(f"Deployment-change snapshot: {deployment_change.snapshot_id}")
            print(f"Failure snapshot: {failure.snapshot_id}")
            derived_change_count = (
                deployment_checkpoint.detected_change_count
                + failure_checkpoint.detected_change_count
            )
            if derived_change_count:
                print(
                    "Changes derived on this run: "
                    f"{derived_change_count}"
                )
            elif deployment_checkpoint.reused and failure_checkpoint.reused:
                print("Existing deployment-change and failure snapshots reused.")
            if batch is None:
                print("Existing failure signal and incident reused.")
            else:
                print(
                    f"Failure signals received: {batch.received_count}; "
                    f"incidents created: {batch.incident_created_count}; "
                    f"incidents correlated: {batch.incident_correlated_count}."
                )
            print("Local demo seed completed.")
        finally:
            reset_authorization_context(context_token)


if __name__ == "__main__":
    main()
