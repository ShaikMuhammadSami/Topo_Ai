"""Independent closure accounting; behavior is exercised in the sibling corpus."""

import ast
from collections import Counter
import json
from pathlib import Path

from app.db import models
from app.security.tenant_context import require_tenant_context
from app.security.tenant_routing import classify_tenant_route
from test_domain_tenant_enforcement import tenant_app, sqlite_tenant_app
from test_authentication_acceptance import _registered_routes

APP = Path(__file__).resolve().parents[1] / "app"


def dependent(node, function):
    return node.call is function or any(dependent(child, function) for child in node.dependencies)


def test_current_route_catalog_has_no_deferred_or_unknown_authority(tenant_app):
    application, _, _ = tenant_app
    catalog = []
    for route in _registered_routes(application):
        for method in sorted(route.methods):
            domain = classify_tenant_route(method, route.path)
            assert domain is not None, (method, route.path)
            if domain.value == "PH3D_TENANT_REQUIRED":
                assert dependent(route.dependant, require_tenant_context), route.path
            catalog.append((method, route.path, domain.value))
    assert Counter(row[2] for row in catalog) == {
        "PH3D_TENANT_REQUIRED": 116, "MACHINE_BOUND": 9,
        "TENANT_CONTROL": 7, "SECURITY_GLOBAL": 9, "PUBLIC": 2,
    }
    assert len(set(catalog)) == len(catalog) == 143
    print("PH3G_ROUTE_CATALOG " + json.dumps(sorted(catalog)))


def test_repository_entrypoints_and_raw_sql_have_explicit_accounting():
    entries, exceptions = [], []
    for path in sorted((APP / "repositories").glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            if not any(arg.annotation is not None and ast.unparse(arg.annotation) == "Session" for arg in args):
                continue
            name = path.stem + "." + node.name
            entries.append(name)
            if "tenant_id" not in [arg.arg for arg in args]:
                exceptions.append(name)
    assert set(exceptions) == {
        "agent_repository.enroll_agent", "agent_repository.authenticate_agent",
        "change_source_repository.load_change_source_for_authentication",
        "auth_api_credential_repository.add_auth_api_credential",
        "auth_api_credential_repository.load_auth_api_credential",
        "auth_api_credential_repository.load_auth_api_credential_by_digest",
        "auth_api_credential_repository.update_auth_api_credential_last_used",
        "auth_api_credential_repository.active_human_credentials",
        "auth_session_repository.add_auth_session", "auth_session_repository.load_auth_session",
        "auth_session_repository.load_auth_session_by_secret_digest",
        "tenant_repository.add_tenant", "tenant_repository.add_tenant_membership",
        "tenant_repository.list_active_tenants_for_principal", "tenant_repository.add_service_api_tenant_binding",
        "tenant_repository.load_service_api_tenant_binding", "tenant_repository.service_binding_tenant_ids",
        "principal_identity_repository.add_principal",
        "principal_identity_repository.add_external_identity",
        "principal_identity_repository.load_principal",
        "principal_identity_repository.load_active_principal",
        "principal_identity_repository.load_active_principal_for_update",
        "principal_identity_repository.load_external_identity",
        "principal_identity_repository.load_active_external_identity",
        "principal_identity_repository.list_external_identities_for_principal",
        "tenant_repository.service_principal_tenant_ids",
        "authority_repository.load_service_permission_assignment",
        "authority_repository.add_service_permission_assignment",
        "authority_repository.compare_and_set_service_permissions",
        "authority_repository.load_installation_operator_assignment",
        "authority_repository.add_installation_operator_assignment",
    }
    raw, legacy_queries, llm = [], [], []
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name == "text" or name.endswith(".exec_driver_sql"):
                raw.append((path.relative_to(APP).as_posix(), node.lineno))
            if name.endswith(".query"):
                legacy_queries.append((path.relative_to(APP).as_posix(), node.lineno))
            if name in {"generate_openai_text", "generate_openai_structured"} or name.endswith(".chat.completions.create"):
                llm.append((path.stem, node.lineno, name))
    assert [path for path, _ in raw] == ["db/schema_management.py"]
    assert [path for path, _ in legacy_queries] == ["repositories/topology_snapshot_repository.py"]
    assert len(llm) == 12  # eight central callers + four legacy Groq branches
    assert len(models.Base.metadata.tables) == 49
    owned = [t for t in models.Base.metadata.tables.values() if "tenant_id" in t.c and t.name not in {
        "tenants", "tenant_memberships", "service_api_tenant_bindings", "secret_records"}]
    # PH-4B's explicit dual-scope store is not an ordinary PH-3 domain table.
    assert models.Base.metadata.tables["secret_records"].c.tenant_id.nullable
    assert "tenant_id" not in models.Base.metadata.tables["secret_versions"].c
    assert len(owned) == 38
    assert all(not t.c.tenant_id.nullable and t.c.tenant_id.default is None and t.c.tenant_id.server_default is None for t in owned)
    print("PH3G_STATIC_INVENTORY " + json.dumps({"repository_audited": len(entries),
        "explicit_tenant": len(entries) - len(exceptions), "classified_exceptions": exceptions,
        "raw_sql": raw, "legacy_scoped_query": legacy_queries, "llm_calls": llm}, sort_keys=True))
