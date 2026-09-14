"""PH-6D frozen authority, sink, transport and bypass contract acceptance."""

from __future__ import annotations

import ast
from pathlib import Path

import httpcore
import httpx

from app.db.database import Base
from app.db.models import SecurityAuditEventRecord
from app.db.schema_management import script_directory
from app.models.security_audit import SecurityAuditAction, SecurityAuditReason
from app.security.authorization_plan import (
    CRITICAL_OPERATION_PLAN,
    ROUTE_AUTHORIZATION_PLAN,
)
from app.security.authorization_policy import Permission
from app.security.customer_data_policy import (
    EXTERNAL_DATA_SINK_POLICIES,
    ExternalDataSink,
)
from app.security.egress_policy import EGRESS_PROFILES, EgressPurpose
from app.security.llm_data_boundary import LLMEgressPurpose


REPOSITORY = Path(__file__).resolve().parents[2]
BACKEND_APP = REPOSITORY / "backend/app"
LLM_SERVICES = (
    "incident_explanation.py",
    "incident_copilot.py",
    "investigation_planner.py",
    "post_incident_report.py",
    "execution_readiness.py",
    "incident_briefing.py",
    "incident_similarity.py",
    "response_intelligence.py",
)


def _python_sources() -> dict[str, str]:
    return {
        path.relative_to(BACKEND_APP).as_posix(): path.read_text(encoding="utf-8")
        for path in BACKEND_APP.rglob("*.py")
        if "__pycache__" not in path.parts
    }


def test_dependency_transport_versions_and_six_purposes_are_frozen() -> None:
    assert httpx.__version__ == "0.28.1"
    assert httpcore.__version__ == "1.0.9"
    assert set(EGRESS_PROFILES) == set(EgressPurpose)
    assert len(EgressPurpose) == 6
    assert {item.value for item in EgressPurpose} == {
        "GITHUB_API_JSON_READ",
        "GITHUB_SOURCE_CONTENT_READ",
        "GITHUB_ARTIFACT_DOWNLOAD",
        "TENANT_WEBHOOK_DELIVERY",
        "OPENAI_PROVIDER",
        "GROQ_PROVIDER",
    }


def test_external_sink_and_typed_llm_contracts_are_closed() -> None:
    assert set(EXTERNAL_DATA_SINK_POLICIES) == set(ExternalDataSink)
    assert len(ExternalDataSink) == 5
    assert len(LLMEgressPurpose) == 8
    assert all(
        "build_safe_llm_request" in (
            BACKEND_APP / "services" / service
        ).read_text(encoding="utf-8")
        for service in LLM_SERVICES
    )


def test_no_uncontrolled_direct_server_http_or_generic_bypass_flag() -> None:
    sources = _python_sources()
    direct_httpx = {
        name for name, source in sources.items() if "httpx.Client(" in source
    }
    assert direct_httpx == {"services/egress_http.py"}
    assert {
        name for name, source in sources.items() if "OpenAI(" in source
    } == {"services/llm_client.py"}
    assert {
        name for name, source in sources.items() if "Groq(" in source
    } == {"services/llm_client.py"}
    joined = "\n".join(
        source
        for name, source in sources.items()
        if name != "security/egress_inventory.py"
    ).casefold()
    for marker in (
        "skip_ssrf",
        "bypass_egress",
        "allow_private",
        "allow_any_host",
        "disable_dns_check",
        "unsafe_transport",
        "verify=false",
        "verify = false",
        "trust_env=true",
        "trust_env = true",
        "follow_redirects=true",
        "follow_redirects = true",
    ):
        assert marker not in joined


def test_no_direct_llm_content_bypass_tool_execution_or_arbitrary_base_url() -> None:
    for service in LLM_SERVICES:
        source = (BACKEND_APP / "services" / service).read_text(encoding="utf-8")
        assert "client.chat.completions.create(" not in source
        assert ".responses.create(" not in source
        assert ".responses.parse(" not in source
        assert "create_groq_client" not in source
    llm_client = (BACKEND_APP / "services/llm_client.py").read_text(
        encoding="utf-8"
    )
    assert "request: SafeLLMRequest" in llm_client
    assert "base_url=" not in llm_client
    for marker in (
        "tools=",
        "functions=",
        "tool_choice",
        "function_call",
    ):
        assert marker not in llm_client


def test_provider_dispatch_accepts_no_generic_dictionary_context() -> None:
    tree = ast.parse(
        (BACKEND_APP / "services/llm_client.py").read_text(encoding="utf-8")
    )
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        name for name in functions if name.startswith("generate_")
    } == {
        "generate_openai_text",
        "generate_openai_structured",
        "generate_groq_structured",
    }
    for name in (
        "generate_openai_text",
        "generate_openai_structured",
        "generate_groq_structured",
    ):
        annotations = {
            argument.arg: ast.unparse(argument.annotation)
            for argument in functions[name].args.kwonlyargs
            if argument.annotation is not None
        }
        assert annotations["request"] == "SafeLLMRequest"


def test_authenticated_frontend_has_no_analytics_sink_or_identifier_events() -> None:
    frontend = REPOSITORY / "frontend"
    product_sources = {
        path.relative_to(frontend).as_posix(): path.read_text(encoding="utf-8")
        for root in (frontend / "app", frontend / "components", frontend / "lib")
        if root.exists()
        for path in root.rglob("*.ts*")
    }
    joined = "\n".join(product_sources.values())
    for marker in (
        "@vercel/analytics",
        "<Analytics",
        "analytics.track",
        "mixpanel",
        "posthog",
        "amplitude",
        "gtag(",
    ):
        assert marker not in joined


def test_route_operation_permission_audit_and_schema_custody() -> None:
    assert len(ROUTE_AUTHORIZATION_PLAN) == 144
    assert len(CRITICAL_OPERATION_PLAN) == 98
    assert len(Permission) == 18
    assert sum(item.value.startswith("execution.") for item in Permission) == 0
    assert len(SecurityAuditAction) == 33
    assert len(SecurityAuditReason) == 11
    assert len(SecurityAuditEventRecord.__table__.columns) == 15
    assert script_directory().get_heads() == ["0015_security_audit"]
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844


def test_server_policy_is_separate_from_trusted_non_http_boundaries() -> None:
    inventory = (BACKEND_APP / "security/egress_inventory.py").read_text(
        encoding="utf-8"
    )
    assert "server-kubernetes" in inventory
    assert "agent-kubernetes" in inventory
    assert "agent-aws" in inventory
    assert "agent-azure" in inventory
    assert "agent-gcp" in inventory
    assert "cli-topo" in inventory
    assert "browser-topo" in inventory
    assert "DATABASE_URL" not in (
        BACKEND_APP / "security/egress_policy.py"
    ).read_text(encoding="utf-8")

