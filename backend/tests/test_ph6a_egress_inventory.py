"""PH-6A outbound callsite and frozen-foundation contract tests."""

from __future__ import annotations

import re
from pathlib import Path

from app.db.database import Base
from app.db.schema_management import script_directory
from app.models.security_audit import SecurityAuditAction, SecurityAuditReason
from app.security.authorization_plan import (
    CRITICAL_OPERATION_PLAN,
    ROUTE_AUTHORIZATION_PLAN,
)
from app.security.authorization_policy import Permission
from app.security.egress_inventory import (
    EGRESS_CALLSITES,
    NETWORK_CAPABLE_SOURCE_FILES,
    NON_EGRESS_REVIEWED_SOURCE_FILES,
    DestinationOwnership,
    DestinationRisk,
    RuntimeComponent,
    callsite_counts,
    destination_counts,
    risk_counts,
)


REPOSITORY = Path(__file__).resolve().parents[2]
PYTHON_ROOTS = ("backend/app", "agent/src", "cli/src", "evaluation")
NETWORK_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:"
    r"httpx|requests|aiohttp|urllib\.request|urllib3|socket|grpc|websockets?|"
    r"openai|groq|kubernetes|boto3|botocore|azure\.|google\.|docker"
    r")(?:\.|\s|$)",
    re.MULTILINE,
)


def _production_python_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root_name in PYTHON_ROOTS:
        root = REPOSITORY / root_name
        for path in root.rglob("*.py"):
            parts = set(path.parts)
            if "tests" in parts or ".venv" in parts or "__pycache__" in parts:
                continue
            files.append(path)
    return tuple(files)


def test_callsite_inventory_is_closed_and_has_no_unknowns() -> None:
    ids = [item.callsite_id for item in EGRESS_CALLSITES]
    assert len(ids) == len(set(ids)) == 103
    assert callsite_counts() == {
        RuntimeComponent.SERVER_PRODUCTION_EGRESS: 28,
        RuntimeComponent.AGENT_CONTROLLED_EGRESS: 64,
        RuntimeComponent.CLI_USER_DIRECTED_EGRESS: 1,
        RuntimeComponent.BROWSER_CLIENT_EGRESS: 2,
        RuntimeComponent.EVALUATION_TEST_ONLY: 8,
        RuntimeComponent.DEAD_OR_UNREACHABLE: 0,
        RuntimeComponent.UNKNOWN: 0,
    }
    assert destination_counts() == {
        DestinationOwnership.CODE_FIXED: 0,
        DestinationOwnership.INSTALLATION_CONFIGURED: 3,
        DestinationOwnership.TENANT_ADMIN_CONFIGURED: 1,
        DestinationOwnership.PERSISTED_TRUSTED_RESOURCE: 0,
        DestinationOwnership.REMOTE_RESPONSE_DERIVED: 24,
        DestinationOwnership.REQUEST_OR_PAYLOAD_DERIVED: 0,
        DestinationOwnership.NONE: 0,
        DestinationOwnership.UNKNOWN: 0,
    }
    assert risk_counts() == {
        DestinationRisk.LOW: 0,
        DestinationRisk.MEDIUM: 3,
        DestinationRisk.HIGH: 24,
        DestinationRisk.CRITICAL: 1,
    }

    for item in EGRESS_CALLSITES:
        assert (REPOSITORY / item.source_file).is_file(), item.callsite_id
        assert item.symbol and item.library_client and item.method_protocol
        assert item.destination_source and item.schemes
        assert item.host_source and item.port_source and item.path_source
        assert item.query_source and item.body_source and item.headers_source
        assert item.credential_source and item.redirect_behavior
        assert item.tls_behavior and item.proxy_behavior and item.timeout_behavior
        assert item.response_size_behavior and item.response_consumed
        assert item.credential_binding
        assert item.component is not RuntimeComponent.UNKNOWN
        assert item.destination_ownership is not DestinationOwnership.UNKNOWN
        if item.component is RuntimeComponent.SERVER_PRODUCTION_EGRESS:
            assert item.destination_ownership is not DestinationOwnership.NONE


def test_network_capable_imports_and_browser_fetch_are_reviewed() -> None:
    discovered = {
        path.relative_to(REPOSITORY).as_posix()
        for path in _production_python_files()
        if NETWORK_IMPORT.search(path.read_text(encoding="utf-8"))
    }
    reviewed = NETWORK_CAPABLE_SOURCE_FILES | NON_EGRESS_REVIEWED_SOURCE_FILES
    assert not discovered - reviewed, sorted(discovered - reviewed)

    frontend_fetch = []
    for path in (REPOSITORY / "frontend").rglob("*.ts*"):
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        if re.search(r"\bfetch\s*\(", path.read_text(encoding="utf-8")):
            frontend_fetch.append(path.relative_to(REPOSITORY).as_posix())
    assert frontend_fetch == ["frontend/lib/topo-api.ts"]
    layout = (REPOSITORY / "frontend/app/layout.tsx").read_text(encoding="utf-8")
    assert "@vercel/analytics" not in layout
    assert "<Analytics" not in layout


def test_direct_server_dispatch_sites_are_centralized_after_ph6b() -> None:
    expected = {
        "backend/app/connectors/github_connector.py": {"httpx.get(": 0, "httpx.stream(": 0},
        "backend/app/services/webhook_delivery.py": {"httpx.Client(": 0},
        "backend/app/services/egress_http.py": {"httpx.Client(": 1},
        "backend/app/services/llm_client.py": {
            ".responses.create(": 1,
            ".responses.parse(": 1,
            ".chat.completions.create(": 1,
        },
        "backend/app/services/incident_copilot.py": {
            "client.chat.completions.create(": 0,
            "Groq(": 0,
        },
        "backend/app/services/incident_explanation.py": {
            "client.chat.completions.create(": 0,
            "Groq(": 0,
        },
        "backend/app/services/investigation_planner.py": {
            "client.chat.completions.create(": 0,
            "Groq(": 0,
        },
        "backend/app/services/post_incident_report.py": {
            "client.chat.completions.create(": 0,
            "Groq(": 0,
        },
        "agent/src/topo_agent/client.py": {
            "httpx.Client(": 1,
            "self.client.request(": 1,
        },
        "agent/src/topo_agent/change_watch_azure.py": {
            "httpx.Client(": 1,
            "client.get(": 1,
        },
        "cli/src/topo_cli/client.py": {
            "httpx.Client(": 1,
            "self._client.request(": 2,
        },
        "evaluation/topo_client.py": {
            "urllib.request.Request(": 1,
            "urllib.request.urlopen(": 1,
        },
    }
    for relative, markers in expected.items():
        text = (REPOSITORY / relative).read_text(encoding="utf-8")
        for marker, count in markers.items():
            assert text.count(marker) == count, (relative, marker)


def test_ph6a_does_not_change_frozen_security_or_schema_counts() -> None:
    assert len(ROUTE_AUTHORIZATION_PLAN) == 143
    assert len(CRITICAL_OPERATION_PLAN) == 98
    assert len(Permission) == 18
    assert len(SecurityAuditAction) == 33
    assert len(SecurityAuditReason) == 11
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
    assert script_directory().get_heads() == ["0015_security_audit"]
