"""PH-5E proof that cross-tenant targets remain indistinguishable from absence."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import SecurityAuditEventRecord
from test_domain_tenant_enforcement import tenant_app, two_tenants
from test_machine_tenant_binding import source
from test_tenant_foundation import _bearer, tenant_app as sqlite_tenant_app


def test_change_source_foreign_and_absent_targets_match_without_audit(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    foreign_id = source(client, tokens["other_admin"], tenant_b)
    headers = _bearer(tokens["bootstrap"], tenant_a)
    with factory() as session:
        before = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )
    foreign = client.get(f"/api/v1/change-sources/{foreign_id}", headers=headers)
    absent = client.get(
        "/api/v1/change-sources/change-source:00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert foreign.status_code == absent.status_code == 404
    assert foreign.content == absent.content
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        ) == before


def test_membership_foreign_and_absent_mutations_match_without_audit(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    created = client.post(
        "/api/v1/tenant-memberships",
        headers=_bearer(tokens["other_admin"], tenant_b),
        json={"subject": "ph5e:masked-member", "role": "tenant_viewer"},
    )
    assert created.status_code == 200
    membership_id = created.json()["membership_id"]
    headers = _bearer(tokens["bootstrap"], tenant_a)
    with factory() as session:
        before = session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        )
    foreign = client.post(
        f"/api/v1/tenant-memberships/{membership_id}/disable", headers=headers
    )
    absent = client.post(
        "/api/v1/tenant-memberships/tenant-membership:00000000-0000-0000-0000-000000000000/disable",
        headers=headers,
    )
    assert foreign.status_code == absent.status_code == 404
    assert foreign.content == absent.content
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(SecurityAuditEventRecord)
        ) == before
