"""PH-6A frozen outbound-network and customer-data inventory.

This module is descriptive only.  It is deliberately not imported by a
runtime request path and does not authorize, create, or dispatch connections.
PH-6B owns transport enforcement; PH-6C owns external-LLM envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RuntimeComponent(StrEnum):
    SERVER_PRODUCTION_EGRESS = "SERVER_PRODUCTION_EGRESS"
    AGENT_CONTROLLED_EGRESS = "AGENT_CONTROLLED_EGRESS"
    CLI_USER_DIRECTED_EGRESS = "CLI_USER_DIRECTED_EGRESS"
    BROWSER_CLIENT_EGRESS = "BROWSER_CLIENT_EGRESS"
    EVALUATION_TEST_ONLY = "EVALUATION_TEST_ONLY"
    DEAD_OR_UNREACHABLE = "DEAD_OR_UNREACHABLE"
    UNKNOWN = "UNKNOWN"


class DestinationOwnership(StrEnum):
    CODE_FIXED = "CODE_FIXED"
    INSTALLATION_CONFIGURED = "INSTALLATION_CONFIGURED"
    TENANT_ADMIN_CONFIGURED = "TENANT_ADMIN_CONFIGURED"
    PERSISTED_TRUSTED_RESOURCE = "PERSISTED_TRUSTED_RESOURCE"
    REMOTE_RESPONSE_DERIVED = "REMOTE_RESPONSE_DERIVED"
    REQUEST_OR_PAYLOAD_DERIVED = "REQUEST_OR_PAYLOAD_DERIVED"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class DestinationRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CustomerDataClass(StrEnum):
    PUBLIC_SYSTEM_DATA = "PUBLIC_SYSTEM_DATA"
    TOPO_CONTROL_METADATA = "TOPO_CONTROL_METADATA"
    TENANT_OPERATIONAL_METADATA = "TENANT_OPERATIONAL_METADATA"
    CUSTOMER_STRUCTURED_OPERATIONAL_DATA = (
        "CUSTOMER_STRUCTURED_OPERATIONAL_DATA"
    )
    CUSTOMER_USER_AUTHORED_CONTENT = "CUSTOMER_USER_AUTHORED_CONTENT"
    RAW_CUSTOMER_PAYLOAD = "RAW_CUSTOMER_PAYLOAD"
    AUTHENTICATION_SECRET = "AUTHENTICATION_SECRET"
    SECRET_MATERIAL = "SECRET_MATERIAL"


@dataclass(frozen=True)
class EgressCallsite:
    callsite_id: str
    source_file: str
    symbol: str
    component: RuntimeComponent
    library_client: str
    synchronous: bool
    method_protocol: str
    destination_source: str
    destination_ownership: DestinationOwnership
    destination_risk: DestinationRisk
    schemes: tuple[str, ...]
    host_source: str
    port_source: str
    path_source: str
    query_source: str
    body_source: str
    headers_source: str
    credential_source: str
    tenant_controlled: bool
    installation_controlled: bool
    resource_or_payload_controlled: bool
    code_fixed: bool
    redirect_behavior: str
    tls_behavior: str
    proxy_behavior: str
    timeout_behavior: str
    response_size_behavior: str
    data_classes: frozenset[CustomerDataClass]
    secret_classes: frozenset[CustomerDataClass]
    response_consumed: str
    destination_can_change_after_initial_request: bool
    credential_binding: str
    notes: str


@dataclass(frozen=True)
class LlmPurpose:
    purpose_id: str
    source_file: str
    symbol: str
    provider_paths: tuple[str, ...]
    input_source_fields: str
    raw_payload_reachable: bool
    free_form_text_reachable: bool
    user_authored_content: bool
    tenant_filtering_point: str
    current_sanitizer: str
    current_bounds: str
    prompt_logging: str
    response_logging: str
    request_persistence: str
    response_persistence: str
    api_key_source: str
    retry_timeout_response_bound: str
    downstream_consumers: str


@dataclass(frozen=True)
class ExternalDataSink:
    sink_id: str
    destination: str
    components: tuple[RuntimeComponent, ...]
    data_classes: frozenset[CustomerDataClass]
    credential_binding: str


def _entry(
    callsite_id: str,
    source_file: str,
    symbol: str,
    component: RuntimeComponent,
    library_client: str,
    method_protocol: str,
    *,
    destination_source: str,
    ownership: DestinationOwnership,
    risk: DestinationRisk,
    schemes: tuple[str, ...],
    host_source: str,
    port_source: str,
    path_source: str,
    query_source: str = "none",
    body_source: str = "none",
    headers_source: str = "library/provider defaults",
    credential_source: str = "none",
    tenant_controlled: bool = False,
    installation_controlled: bool = False,
    resource_or_payload_controlled: bool = False,
    code_fixed: bool = False,
    redirects: str = "not applicable",
    tls: str = "not applicable",
    proxy: str = "not applicable",
    timeout: str = "not explicitly bounded",
    response_size: str = "not explicitly bounded",
    data: tuple[CustomerDataClass, ...] = (),
    secrets: tuple[CustomerDataClass, ...] = (),
    response: str = "provider result consumed by caller",
    destination_changes: bool = False,
    credential_binding: str = "no credential",
    notes: str = "",
) -> EgressCallsite:
    return EgressCallsite(
        callsite_id=callsite_id,
        source_file=source_file,
        symbol=symbol,
        component=component,
        library_client=library_client,
        synchronous=True,
        method_protocol=method_protocol,
        destination_source=destination_source,
        destination_ownership=ownership,
        destination_risk=risk,
        schemes=schemes,
        host_source=host_source,
        port_source=port_source,
        path_source=path_source,
        query_source=query_source,
        body_source=body_source,
        headers_source=headers_source,
        credential_source=credential_source,
        tenant_controlled=tenant_controlled,
        installation_controlled=installation_controlled,
        resource_or_payload_controlled=resource_or_payload_controlled,
        code_fixed=code_fixed,
        redirect_behavior=redirects,
        tls_behavior=tls,
        proxy_behavior=proxy,
        timeout_behavior=timeout,
        response_size_behavior=response_size,
        data_classes=frozenset(data),
        secret_classes=frozenset(secrets),
        response_consumed=response,
        destination_can_change_after_initial_request=destination_changes,
        credential_binding=credential_binding,
        notes=notes,
    )


SERVER = RuntimeComponent.SERVER_PRODUCTION_EGRESS
AGENT = RuntimeComponent.AGENT_CONTROLLED_EGRESS
CLI = RuntimeComponent.CLI_USER_DIRECTED_EGRESS
BROWSER = RuntimeComponent.BROWSER_CLIENT_EGRESS
EVAL = RuntimeComponent.EVALUATION_TEST_ONLY

PUBLIC = CustomerDataClass.PUBLIC_SYSTEM_DATA
CONTROL = CustomerDataClass.TOPO_CONTROL_METADATA
TENANT_META = CustomerDataClass.TENANT_OPERATIONAL_METADATA
STRUCTURED = CustomerDataClass.CUSTOMER_STRUCTURED_OPERATIONAL_DATA
USER_TEXT = CustomerDataClass.CUSTOMER_USER_AUTHORED_CONTENT
RAW = CustomerDataClass.RAW_CUSTOMER_PAYLOAD
AUTH = CustomerDataClass.AUTHENTICATION_SECRET
SECRET = CustomerDataClass.SECRET_MATERIAL


_SERVER_BASE = (
    _entry(
        "server.database.engine-connect",
        "backend/app/db/database.py",
        "create_engine",
        SERVER,
        "SQLAlchemy + selected DBAPI driver",
        "database driver protocol",
        destination_source="TOPO_DATABASE_URL",
        ownership=DestinationOwnership.INSTALLATION_CONFIGURED,
        risk=DestinationRisk.MEDIUM,
        schemes=("sqlite", "postgresql"),
        host_source="installation database URL; none for SQLite",
        port_source="installation database URL or driver default",
        path_source="database name/path from installation URL",
        query_source="driver options from installation URL",
        headers_source="database wire protocol",
        credential_source="database URL / deployment secret",
        installation_controlled=True,
        tls="DBAPI/URL configuration; PostgreSQL production policy is installation-owned",
        proxy="database driver; HTTP proxy environment is not used",
        timeout="pool_pre_ping enabled; no explicit network connect/read timeout",
        response_size="query-specific; ORM rows are not centrally bounded",
        data=(TENANT_META, STRUCTURED, RAW),
        secrets=(SECRET,),
        response="SQL rows and transaction status",
        credential_binding="database credential is embedded in the installation DB authority",
        notes="Trusted datastore connection, not general-purpose HTTP egress.",
    ),
    _entry(
        "server.github.api-get",
        "backend/app/connectors/github_connector.py",
        "GitHubConnector._get",
        SERVER,
        "httpx.get",
        "HTTP GET",
        destination_source="TOPO_GITHUB_API_URL plus code-owned repository API path",
        ownership=DestinationOwnership.INSTALLATION_CONFIGURED,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https"),
        host_source="validated installation GitHub API base URL",
        port_source="base URL/default",
        path_source="code template plus configured owner/repository/provider IDs",
        query_source="bounded provider API parameters",
        headers_source="code-fixed GitHub Accept/version/User-Agent",
        credential_source="SecretStore installation secret github",
        installation_controlled=True,
        redirects="disabled; every 3xx rejected",
        tls="httpx verification default for HTTPS; HTTP is currently accepted by base validator",
        proxy="httpx top-level default trust_env=True",
        timeout="single scalar TOPO_GITHUB_TIMEOUT_SECONDS, default 20s",
        response_size="response.json() reads/decompresses the complete response",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="provider JSON metadata",
        credential_binding="GitHub bearer token is attached only to configured API base requests",
    ),
    _entry(
        "server.github.bounded-content-get",
        "backend/app/connectors/github_connector.py",
        "GitHubConnector._get_bounded_content",
        SERVER,
        "httpx.stream",
        "HTTP GET",
        destination_source="TOPO_GITHUB_API_URL plus code-owned contents path",
        ownership=DestinationOwnership.INSTALLATION_CONFIGURED,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https"),
        host_source="validated installation GitHub API base URL",
        port_source="base URL/default",
        path_source="repository content path from provider change metadata after path validation",
        query_source="code-owned ref parameter containing commit SHA",
        headers_source="code-fixed GitHub headers",
        credential_source="SecretStore installation secret github",
        installation_controlled=True,
        resource_or_payload_controlled=True,
        redirects="disabled; every 3xx rejected",
        tls="httpx verification default for HTTPS",
        proxy="httpx top-level default trust_env=True",
        timeout="single scalar configured timeout",
        response_size="streamed and capped by MAX_GITHUB_CONTENT_BYTES after decompression",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="bounded source file bytes",
        credential_binding="GitHub credential remains on configured API authority",
    ),
    _entry(
        "server.github.artifact-redirect-get",
        "backend/app/connectors/github_connector.py",
        "GitHubConnector.download_actions_artifact",
        SERVER,
        "httpx.get",
        "HTTP GET",
        destination_source="configured GitHub API then remote Location responses",
        ownership=DestinationOwnership.REMOTE_RESPONSE_DERIVED,
        risk=DestinationRisk.HIGH,
        schemes=("http", "https"),
        host_source="initial GitHub base; subsequent provider Location hostname",
        port_source="initial/default or Location URL",
        path_source="code-owned artifact path then provider Location",
        headers_source="GitHub auth initially; non-auth Accept/User-Agent after origin change",
        credential_source="SecretStore github secret only while origin is unchanged",
        installation_controlled=True,
        resource_or_payload_controlled=True,
        redirects="manual maximum four hops; validates URL shape; strips Authorization cross-origin",
        tls="httpx default for HTTPS; redirect validation currently permits HTTP",
        proxy="httpx top-level default trust_env=True",
        timeout="single scalar configured timeout per hop",
        response_size="response.content then 32 MiB cap; declared length prechecked",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="bounded Docker build artifact bytes",
        destination_changes=True,
        credential_binding="credential is same-origin only; cross-origin hop gets no Authorization",
        notes="PH-6B must validate every actual redirect destination/address and forbid downgrade.",
    ),
    _entry(
        "server.webhook.delivery-post",
        "backend/app/services/webhook_delivery.py",
        "deliver_event_to_endpoint",
        SERVER,
        "httpx.Client.post",
        "HTTP POST",
        destination_source="tenant-admin persisted webhook endpoint URL",
        ownership=DestinationOwnership.TENANT_ADMIN_CONFIGURED,
        risk=DestinationRisk.CRITICAL,
        schemes=("http", "https"),
        host_source="tenant-admin URL",
        port_source="tenant-admin URL/default",
        path_source="tenant-admin URL",
        query_source="tenant-admin URL after current credential-shaped query rejection",
        body_source="serialized lifecycle event payload",
        headers_source="code headers plus decrypted protected headers and optional signature",
        credential_source="tenant SecretStore protected-header/signing records",
        tenant_controlled=True,
        resource_or_payload_controlled=True,
        redirects="disabled; 3xx is terminal response",
        tls="httpx verifies HTTPS; current persisted validator also allows HTTP",
        proxy="httpx Client default trust_env=True",
        timeout="bounded scalar clamped to 1-30s",
        response_size="body not consumed; connection may still receive protocol bytes",
        data=(CONTROL, TENANT_META, STRUCTURED, RAW),
        secrets=(AUTH, SECRET),
        response="status code only",
        credential_binding="currently bound to persisted URL string; PH-6B canonical authority required",
        notes="Accepted finding. Architect froze V1 as public HTTPS DNS host:443 only; PH-6B owns closure.",
    ),
    _entry(
        "server.llm.openai-text",
        "backend/app/services/llm_client.py",
        "generate_openai_text",
        SERVER,
        "OpenAI Responses SDK",
        "HTTPS POST",
        destination_source="OpenAI SDK default endpoint then SDK-followed Location responses",
        ownership=DestinationOwnership.REMOTE_RESPONSE_DERIVED,
        risk=DestinationRisk.HIGH,
        schemes=("https",),
        host_source="OpenAI SDK default",
        port_source="443",
        path_source="OpenAI Responses API SDK",
        body_source="system instructions plus sanitized structured payload",
        headers_source="OpenAI SDK",
        credential_source="SecretStore installation secret openai",
        resource_or_payload_controlled=True,
        redirects="OpenAI DefaultHttpxClient sets follow_redirects=True; HTTPX default maximum 20",
        tls="SDK default certificate/hostname verification",
        proxy="SDK/httpx environment behavior is not overridden",
        timeout="60s client timeout; max_retries=2",
        response_size="bounded by max_output_tokens requested by caller",
        data=(CONTROL, TENANT_META, STRUCTURED, USER_TEXT, RAW),
        secrets=(AUTH,),
        response="generated text",
        destination_changes=True,
        credential_binding="OpenAI key starts on SDK authority; HTTPX strips Authorization cross-origin",
        notes="RAW is current exposure, forbidden target contract, closure owner PH-6C.",
    ),
    _entry(
        "server.llm.openai-structured",
        "backend/app/services/llm_client.py",
        "generate_openai_structured",
        SERVER,
        "OpenAI Responses SDK",
        "HTTPS POST",
        destination_source="OpenAI SDK default endpoint then SDK-followed Location responses",
        ownership=DestinationOwnership.REMOTE_RESPONSE_DERIVED,
        risk=DestinationRisk.HIGH,
        schemes=("https",),
        host_source="OpenAI SDK default",
        port_source="443",
        path_source="OpenAI Responses parse API SDK",
        body_source="system instructions plus sanitize_structured(evidence_payload)",
        headers_source="OpenAI SDK",
        credential_source="SecretStore installation secret openai",
        resource_or_payload_controlled=True,
        redirects="OpenAI DefaultHttpxClient sets follow_redirects=True; HTTPX default maximum 20",
        tls="SDK default certificate/hostname verification",
        proxy="SDK/httpx environment behavior is not overridden",
        timeout="60s client timeout; max_retries=2",
        response_size="max_output_tokens=4000 plus strict response model parse",
        data=(CONTROL, TENANT_META, STRUCTURED, USER_TEXT, RAW),
        secrets=(AUTH,),
        response="validated Pydantic response model",
        destination_changes=True,
        credential_binding="OpenAI key starts on SDK authority; HTTPX strips Authorization cross-origin",
        notes="Opaque payload_json survives the current key scrub; PH-6C must use typed allowlists.",
    ),
)


def _server_groq(
    purpose: str,
    source_file: str,
    symbol: str,
    timeout: str,
) -> EgressCallsite:
    return _entry(
        f"server.llm.groq-{purpose}",
        source_file,
        symbol,
        SERVER,
        "Groq chat-completions SDK",
        "HTTPS POST",
        destination_source="Groq SDK default endpoint then SDK-followed Location responses",
        ownership=DestinationOwnership.REMOTE_RESPONSE_DERIVED,
        risk=DestinationRisk.HIGH,
        schemes=("https",),
        host_source="Groq SDK default",
        port_source="443",
        path_source="Groq chat completions SDK",
        body_source="system prompt and JSON evidence catalog",
        headers_source="Groq SDK",
        credential_source="SecretStore installation secret groq",
        resource_or_payload_controlled=True,
        redirects="Groq DefaultHttpxClient sets follow_redirects=True; HTTPX default maximum 20",
        tls="SDK default certificate/hostname verification",
        proxy="SDK/httpx environment behavior is not overridden",
        timeout=f"{timeout} client timeout; max_retries=2",
        response_size="no max_tokens supplied; strict local JSON model validation follows",
        data=(CONTROL, TENANT_META, STRUCTURED, USER_TEXT, RAW),
        secrets=(AUTH,),
        response="structured generated JSON",
        destination_changes=True,
        credential_binding="Groq key starts on SDK authority; HTTPX strips Authorization cross-origin",
        notes="Direct central-client bypass and current raw evidence reachability; PH-6C owns migration.",
    )


_SERVER_GROQ = (
    _server_groq(
        "copilot",
        "backend/app/services/incident_copilot.py",
        "_groq_answer",
        "60s",
    ),
    _server_groq(
        "explanation",
        "backend/app/services/incident_explanation.py",
        "_groq_explanation",
        "60s",
    ),
    _server_groq(
        "planner",
        "backend/app/services/investigation_planner.py",
        "_groq_plan",
        "60s",
    ),
    _server_groq(
        "report",
        "backend/app/services/post_incident_report.py",
        "_groq_report",
        "90s",
    ),
)


def _kubernetes_call(
    callsite_id: str,
    source_file: str,
    symbol: str,
    component: RuntimeComponent,
) -> EgressCallsite:
    ownership = (
        DestinationOwnership.REMOTE_RESPONSE_DERIVED
        if component is SERVER
        else DestinationOwnership.NONE
    )
    return _entry(
        callsite_id,
        source_file,
        symbol,
        component,
        "Kubernetes Python client",
        "Kubernetes API over HTTP(S)",
        destination_source="in-cluster service configuration or kubeconfig/context",
        ownership=ownership,
        risk=(
            DestinationRisk.HIGH
            if component is SERVER
            else DestinationRisk.MEDIUM
        ),
        schemes=("http", "https"),
        host_source="trusted cluster configuration",
        port_source="cluster configuration/default",
        path_source="SDK operation",
        query_source="namespace/selectors/pagination supplied by collector policy",
        headers_source="Kubernetes SDK",
        credential_source="service account or kubeconfig credential/exec provider",
        installation_controlled=True,
        redirects="urllib3 PoolManager redirect default enabled; Retry removes auth/cookie headers on cross-origin redirect",
        tls="CA and verification behavior from trusted cluster configuration",
        proxy="Kubernetes client/config and urllib3 environment behavior",
        timeout="no per-call timeout supplied by these callsites",
        response_size="list/read result is not centrally byte bounded",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="cluster inventory/event objects",
        destination_changes=True,
        credential_binding="cluster credential and API authority come from the same trusted config",
        notes="Private endpoint is an intentional privileged infrastructure control-plane boundary.",
    )


_BACKEND_KUBERNETES_OPERATIONS = (
    ("collector.version", "backend/app/collectors/kubernetes_collector.py", "connection_information:get_code"),
    ("collector.namespace-read", "backend/app/collectors/kubernetes_collector.py", "_list_namespaces:read_namespace"),
    ("collector.namespace-list", "backend/app/collectors/kubernetes_collector.py", "_list_namespaces:list_namespace"),
    ("collector.deployment-namespaced", "backend/app/collectors/kubernetes_collector.py", "_list_deployments:list_namespaced_deployment"),
    ("collector.deployment-all", "backend/app/collectors/kubernetes_collector.py", "_list_deployments:list_deployment_for_all_namespaces"),
    ("collector.replicaset-namespaced", "backend/app/collectors/kubernetes_collector.py", "_list_replica_sets:list_namespaced_replica_set"),
    ("collector.replicaset-all", "backend/app/collectors/kubernetes_collector.py", "_list_replica_sets:list_replica_set_for_all_namespaces"),
    ("collector.pod-namespaced", "backend/app/collectors/kubernetes_collector.py", "_list_pods:list_namespaced_pod"),
    ("collector.pod-all", "backend/app/collectors/kubernetes_collector.py", "_list_pods:list_pod_for_all_namespaces"),
    ("collector.service-namespaced", "backend/app/collectors/kubernetes_collector.py", "_list_services:list_namespaced_service"),
    ("collector.service-all", "backend/app/collectors/kubernetes_collector.py", "_list_services:list_service_for_all_namespaces"),
    ("events.namespaced", "backend/app/collectors/kubernetes_event_collector.py", "_list_events:list_namespaced_event"),
    ("events.all", "backend/app/collectors/kubernetes_event_collector.py", "_list_events:list_event_for_all_namespaces"),
    ("network.services", "backend/app/services/network_topology_enricher.py", "enrich_network_topology:list_namespaced_service"),
    ("network.pods", "backend/app/services/network_topology_enricher.py", "enrich_network_topology:list_namespaced_pod"),
    ("network.ingresses", "backend/app/services/network_topology_enricher.py", "enrich_network_topology:list_namespaced_ingress"),
    ("network.endpointslices", "backend/app/services/network_topology_enricher.py", "enrich_network_topology:list_namespaced_endpoint_slice"),
)

_SERVER_KUBERNETES = tuple(
    _kubernetes_call(f"server.kubernetes.{suffix}", path, symbol, SERVER)
    for suffix, path, symbol in _BACKEND_KUBERNETES_OPERATIONS
)


def _agent_provider_call(
    provider: str,
    operation: str,
    source_file: str,
    library: str,
    *,
    schemes: tuple[str, ...] = ("https",),
    notes: str = "",
) -> EgressCallsite:
    return _entry(
        f"agent.{provider}.{operation}",
        source_file,
        operation,
        AGENT,
        library,
        "provider SDK/API",
        destination_source="code-fixed provider API plus agent operator account/region/project config",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.LOW,
        schemes=schemes,
        host_source="provider SDK endpoint resolution",
        port_source="provider SDK default",
        path_source="provider SDK operation",
        query_source="agent configured scope and SDK pagination tokens",
        headers_source="provider SDK",
        credential_source="agent workload identity/default credential chain",
        installation_controlled=True,
        redirects="provider SDK behavior; no customer next-link URL is requested directly",
        tls="provider SDK default certificate/hostname verification",
        proxy="provider SDK/environment defaults",
        timeout="provider SDK defaults; plugin retry policies do not add a universal socket timeout",
        response_size="provider page/result is not centrally byte bounded",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="provider inventory or audit records normalized by agent",
        credential_binding="provider SDK credential is bound to the SDK/provider authority",
        notes=notes,
    )


_AGENT_TOPO = (
    _entry(
        "agent.topo-api.request",
        "agent/src/topo_agent/client.py",
        "TopoAgentClient._request",
        AGENT,
        "httpx.Client.request",
        "HTTP request",
        destination_source="agent operator configured Topo backend URL plus code-owned API paths",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https"),
        host_source="agent configuration/CLI",
        port_source="agent configuration/default",
        path_source="code-owned agent/enrollment/snapshot/runtime/change/signal paths",
        query_source="code-owned",
        body_source="agent enrollment, inventory, telemetry, changes, failures, heartbeats",
        headers_source="code-owned content type and bearer Authorization",
        credential_source="agent enrollment token then enrolled agent token",
        installation_controlled=True,
        redirects="disabled",
        tls="verification configurable; explicit insecure mode is operator-controlled",
        proxy="httpx Client default trust_env=True",
        timeout="bounded 60s client timeout; retry helper bounded by config",
        response_size="response.json()/content is not centrally byte bounded",
        data=(CONTROL, TENANT_META, STRUCTURED, RAW),
        secrets=(AUTH,),
        response="Topo control responses and enrollment credential",
        credential_binding="one client/base URL and one agent credential",
    ),
)

_AGENT_CHANGE = (
    _agent_provider_call("aws-cloudtrail", "lookup_events", "agent/src/topo_agent/change_watch_aws.py", "boto3 CloudTrail client"),
    _agent_provider_call("azure-activity", "get_token", "agent/src/topo_agent/change_watch_azure.py", "Azure DefaultAzureCredential"),
    _entry(
        "agent.azure-activity.http-get",
        "agent/src/topo_agent/change_watch_azure.py",
        "AzureActivityChangePoller.poll",
        AGENT,
        "httpx.Client.get",
        "HTTPS GET",
        destination_source="code-fixed management.azure.com URL",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.LOW,
        schemes=("https",),
        host_source="code fixed management.azure.com",
        port_source="443",
        path_source="subscription activityLogs path from configured subscription ID",
        query_source="bounded time/filter query",
        headers_source="Authorization bearer",
        credential_source="Azure DefaultAzureCredential access token",
        installation_controlled=True,
        code_fixed=True,
        redirects="httpx Client default disabled",
        tls="httpx default verification",
        proxy="httpx Client default trust_env=True",
        timeout="30s scalar client timeout",
        response_size="response.json() complete body; no byte bound",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="Azure Activity Log records",
        credential_binding="Azure token audience and code-fixed management authority",
    ),
    _agent_provider_call("gcp-audit", "list_entries", "agent/src/topo_agent/change_watch_gcp.py", "google.cloud.logging_v2.Client"),
    _kubernetes_call("agent.kubernetes-events.namespaced", "agent/src/topo_agent/change_watch_kubernetes.py", "poll:list_namespaced_event", AGENT),
    _kubernetes_call("agent.kubernetes-events.all", "agent/src/topo_agent/change_watch_kubernetes.py", "poll:list_event_for_all_namespaces", AGENT),
)

_AGENT_KUBERNETES_OPERATION_NAMES = (
    "doctor.list_namespace",
    "collect.list_namespace",
    "collect.list_node",
    "collect.deployment_all",
    "collect.deployment_namespaced",
    "collect.replicaset_all",
    "collect.replicaset_namespaced",
    "collect.pod_all",
    "collect.pod_namespaced",
    "collect.service_all",
    "collect.service_namespaced",
    "collect.ingress_all",
    "collect.ingress_namespaced",
    "collect.endpointslice_all",
    "collect.endpointslice_namespaced",
)

_AGENT_KUBERNETES = tuple(
    _kubernetes_call(
        f"agent.kubernetes-discovery.{operation}",
        "agent/src/topo_agent/collector.py",
        operation,
        AGENT,
    )
    for operation in _AGENT_KUBERNETES_OPERATION_NAMES
)

_AGENT_DOCKER = tuple(
    _entry(
        f"agent.docker.{operation}",
        "agent/src/topo_agent/plugins/docker.py",
        operation,
        AGENT,
        "Docker SDK for Python",
        "Docker Engine API",
        destination_source="docker_base_url or docker.from_env",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.MEDIUM,
        schemes=("npipe", "unix", "http", "https"),
        host_source="agent operator Docker configuration/environment",
        port_source="Docker configuration/default",
        path_source="Docker SDK operation",
        headers_source="Docker SDK",
        credential_source="Docker SDK environment/TLS configuration",
        installation_controlled=True,
        redirects="Docker SDK transport behavior",
        tls="Docker SDK/environment configuration",
        proxy="Docker SDK/environment behavior",
        timeout="Docker SDK default",
        response_size="Docker SDK object collection not centrally byte bounded",
        data=(CONTROL, TENANT_META),
        secrets=(AUTH,),
        response="local/container-runtime inventory",
        credential_binding="operator-selected Docker daemon and its SDK credentials",
        notes="Trusted agent-local/runtime control plane; not server-side general HTTP egress.",
    )
    for operation in ("doctor.info", "collect.info", "networks.list", "containers.list")
)

_AWS_OPERATIONS = (
    "sts.assume_role",
    "sts.get_caller_identity",
    "ec2.describe_regions",
    "ec2.describe_vpcs",
    "ec2.describe_subnets",
    "ec2.describe_route_tables",
    "ec2.describe_security_groups",
    "ec2.describe_instances",
    "eks.list_clusters",
    "eks.describe_cluster",
    "eks.list_nodegroups",
    "eks.describe_nodegroup",
    "elbv2.describe_load_balancers",
    "elbv2.describe_tags",
    "elbv2.describe_target_groups",
    "elbv2.describe_target_health",
    "rds.describe_db_instances",
    "rds.list_tags_for_resource",
    "lambda.list_functions",
    "lambda.list_tags",
)

_AGENT_AWS = tuple(
    _agent_provider_call(
        "aws-inventory",
        operation,
        "agent/src/topo_agent/plugins/aws.py",
        "boto3/botocore",
        notes="Default credential chain may intentionally use ECS/EC2 metadata or web identity.",
    )
    for operation in _AWS_OPERATIONS
)

_AZURE_OPERATIONS = (
    "credential.get_token",
    "subscriptions.get",
    "subscriptions.list",
    "resource_graph.resources",
)

_AGENT_AZURE = tuple(
    _agent_provider_call(
        "azure-inventory",
        operation,
        "agent/src/topo_agent/plugins/azure.py",
        "Azure Identity/Resource SDK",
        notes="Managed/workload identity may intentionally use the Azure metadata identity endpoint.",
    )
    for operation in _AZURE_OPERATIONS
)

_GCP_OPERATIONS = (
    "projects.search_projects",
    "projects.get_project",
    "folders.get_folder",
    "organizations.get_organization",
    "networks.list",
    "subnetworks.aggregated_list",
    "firewalls.list",
    "routes.list",
    "instances.aggregated_list",
    "instance_group_managers.aggregated_list",
    "addresses.aggregated_list",
    "forwarding_rules.aggregated_list",
    "gke.list_clusters",
    "asset.search_all_resources",
)

_AGENT_GCP = tuple(
    _agent_provider_call(
        "gcp-inventory",
        operation,
        "agent/src/topo_agent/plugins/gcp.py",
        "Google Cloud Python SDK",
        notes="ADC may intentionally use GCE metadata; optional impersonation remains SDK-controlled.",
    )
    for operation in _GCP_OPERATIONS
)

_USER_CLIENTS = (
    _entry(
        "cli.topo-api.request",
        "cli/src/topo_cli/client.py",
        "TopoClient._request",
        CLI,
        "httpx.Client.request",
        "HTTP request",
        destination_source="local user-selected Topo base URL",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https"),
        host_source="CLI profile/option/environment",
        port_source="user URL/default",
        path_source="code-owned Topo API path",
        query_source="command parameters",
        body_source="command request models and user input",
        headers_source="Topo bearer and tenant headers",
        credential_source="local CLI credential store/environment",
        installation_controlled=True,
        redirects="disabled",
        tls="default verification; explicit local --insecure supported",
        proxy="httpx Client default trust_env=True",
        timeout="bounded user-configured timeout, default 30s; bounded retries",
        response_size="JSON and downloads read fully into memory; no byte cap",
        data=(CONTROL, TENANT_META, STRUCTURED, USER_TEXT),
        secrets=(AUTH,),
        response="Topo API JSON/binary report",
        credential_binding="one CLI client/base authority and credential",
    ),
    _entry(
        "browser.topo-api.fetch",
        "frontend/lib/topo-api.ts",
        "apiFetch",
        BROWSER,
        "browser fetch",
        "same-origin HTTP request",
        destination_source="same browser origin plus required /api/ path",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.LOW,
        schemes=("http", "https"),
        host_source="browser page origin",
        port_source="browser page origin",
        path_source="code caller; helper requires /api/ prefix",
        query_source="UI request parameters",
        body_source="UI request model/user input",
        headers_source="CSRF and tenant selection; browser supplies session cookie",
        credential_source="same-origin HttpOnly session cookie",
        redirects="browser fetch default; final same-origin API handling is browser-controlled",
        tls="browser origin policy",
        proxy="browser/OS policy",
        timeout="no AbortController timeout",
        response_size="response json/blob is not byte bounded",
        data=(CONTROL, TENANT_META, STRUCTURED, USER_TEXT),
        secrets=(AUTH,),
        response="Topo JSON/blob",
        credential_binding="credentials:'same-origin'; no arbitrary absolute destination accepted",
    ),
    _entry(
        "browser.vercel-analytics.pageview",
        "frontend/app/layout.tsx",
        "RootLayout:Analytics",
        BROWSER,
        "@vercel/analytics/next injected browser script",
        "browser script/pageview transport",
        destination_source="code-fixed same-origin /_vercel/insights script; vendor deployment runtime handles collection",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https"),
        host_source="deployed browser application origin/vendor integration",
        port_source="browser application origin",
        path_source="/_vercel/insights script and vendor collection runtime",
        query_source="page navigation metadata; product supplies no custom analytics properties",
        body_source="automatic pageview route/path and browser-generated analytics metadata",
        headers_source="browser/vendor script; no product-forwarded header map",
        credential_source="none explicitly supplied by Topo application code",
        code_fixed=True,
        redirects="browser/vendor script behavior",
        tls="browser origin and vendor certificate policy",
        proxy="browser/OS policy",
        timeout="browser/vendor script behavior; no application timeout",
        response_size="browser/vendor script behavior; no application byte bound",
        data=(PUBLIC, CONTROL, TENANT_META),
        response="analytics script/acknowledgement; not consumed by Topo product logic",
        credential_binding="no Topo provider credential is attached by application code",
        notes="Production-only browser analytics; incident IDs may occur in page paths. Not server SSRF.",
    ),
)


def _evaluation_call(callsite_id: str, source_file: str, symbol: str, client: str) -> EgressCallsite:
    return _entry(
        callsite_id,
        source_file,
        symbol,
        EVAL,
        client,
        "evaluation-only provider/control-plane request",
        destination_source="evaluation operator fixtures/options",
        ownership=DestinationOwnership.NONE,
        risk=DestinationRisk.MEDIUM,
        schemes=("http", "https", "ssh"),
        host_source="evaluation configuration/tool context",
        port_source="evaluation configuration/default",
        path_source="evaluation scenario",
        query_source="evaluation scenario",
        body_source="synthetic evaluation fixtures",
        headers_source="tool/client defaults",
        credential_source="operator development tool credential",
        installation_controlled=True,
        redirects="tool/client behavior",
        tls="tool/client behavior",
        proxy="tool/client environment behavior",
        timeout="scenario/tool-specific bounded process timeout",
        response_size="evaluation artifact/result, not production bounded",
        data=(PUBLIC, CONTROL),
        secrets=(AUTH,),
        response="evaluation truth/receipt",
        credential_binding="local evaluation operator/tool boundary",
        notes="Excluded from production egress policy runtime.",
    )


_EVALUATION = (
    _evaluation_call("evaluation.topo-api", "evaluation/topo_client.py", "TopoClient.request", "urllib.request"),
    _evaluation_call("evaluation.h3.github-cli", "evaluation/h3_runner.py", "GitHub CLI dispatch", "subprocess gh"),
    _evaluation_call("evaluation.h3.docker-cli", "evaluation/h3_runner.py", "Docker CLI dispatch", "subprocess docker"),
    _evaluation_call("evaluation.h3.kubectl-cli", "evaluation/h3_runner.py", "Kubernetes CLI dispatch", "subprocess kubectl"),
    _evaluation_call("evaluation.lineage.github-cli", "evaluation/lineage_runner.py", "GitHub CLI dispatch", "subprocess gh"),
    _evaluation_call("evaluation.lineage.docker-cli", "evaluation/lineage_runner.py", "Docker CLI dispatch", "subprocess docker"),
    _evaluation_call("evaluation.lineage.kubectl-cli", "evaluation/lineage_runner.py", "Kubernetes CLI dispatch", "subprocess kubectl"),
    _evaluation_call("evaluation.runtime.kubectl-cli", "evaluation/runtime_causal_observer.py", "Kubernetes CLI dispatch", "subprocess kubectl"),
)


EGRESS_CALLSITES = (
    *_SERVER_BASE,
    *_SERVER_GROQ,
    *_SERVER_KUBERNETES,
    *_AGENT_TOPO,
    *_AGENT_CHANGE,
    *_AGENT_KUBERNETES,
    *_AGENT_DOCKER,
    *_AGENT_AWS,
    *_AGENT_AZURE,
    *_AGENT_GCP,
    *_USER_CLIENTS,
    *_EVALUATION,
)


NETWORK_CAPABLE_SOURCE_FILES = frozenset(
    item.source_file for item in EGRESS_CALLSITES
) | frozenset({
    "backend/app/security/egress_policy.py",
    "backend/app/services/egress_http.py",
    "backend/app/services/execution_readiness.py",
    "backend/app/services/incident_briefing.py",
    "backend/app/services/incident_similarity.py",
    "backend/app/services/response_intelligence.py",
})

# These files import a network-capable package or URL/socket helper but do not
# themselves dispatch a distinct outbound connection.  They are kept explicit
# so a static scan cannot silently ignore them.
NON_EGRESS_REVIEWED_SOURCE_FILES = frozenset({
    "agent/src/topo_agent/plugins/host.py",  # local hostname/system inventory
    "agent/src/topo_agent/plugins/network.py",  # local interface/hostname inventory
    "agent/src/topo_agent/security.py",  # URL parsing only
    "backend/app/api/kubernetes.py",  # catches SDK exception; collector owns I/O
    "backend/app/api/signals.py",  # catches SDK exception; collector owns I/O
    "backend/app/api/snapshots.py",  # catches SDK exception; collector owns I/O
    "backend/app/security/auth_config.py",  # URL parsing only
    "backend/app/security/secret_redaction.py",  # URL parsing only
    "backend/app/services/canonical_identity.py",  # URL parsing only
    "backend/app/services/github_actions_build_record.py",  # URL parsing only
    "backend/app/services/secret_consumer_policy.py",  # URL parsing only
    "backend/app/services/security_audit.py",  # URL parsing only
    "cli/src/topo_cli/retry.py",  # classifies httpx exceptions only
    "cli/src/topo_cli/security.py",  # URL parsing only
    "evaluation/lineage_provider_truth.py",  # URL parsing only
    "evaluation/runner.py",  # loopback readiness socket only
})


LLM_PURPOSES = (
    LlmPurpose(
        "incident-explanation",
        "backend/app/services/incident_explanation.py",
        "generate_incident_explanation",
        ("openai", "groq-direct"),
        "GroundingEvidence catalog built from incident, signals, changes, topology, RCA, blast radius and investigation evidence",
        True,
        True,
        False,
        "incident and every repository/service input are loaded with authorized tenant_id before evidence construction",
        "OpenAI sanitize_structured; Groq receives selected model_dump evidence; neither removes marker inside payload_json",
        "evidence list capped by TOPO_AI_LLM_MAX_EVIDENCE_ITEMS (default 50); individual opaque evidence strings and Groq response tokens unbounded",
        "none",
        "none",
        "prompt/evidence request is not persisted as provider request",
        "validated explanation plus evidence IDs/evidence JSON persisted",
        "installation SecretStore openai or groq",
        "OpenAI 60s/2 retries/4000 tokens; Groq 60s/2 retries/no max_tokens",
        "incident explanation record/API; deterministic evidence references validated",
    ),
    LlmPurpose(
        "incident-copilot",
        "backend/app/services/incident_copilot.py",
        "answer_copilot_question",
        ("openai", "groq-direct"),
        "authenticated question, last 10 messages, and sanitized GroundingEvidence catalog",
        True,
        True,
        True,
        "tenant-scoped incident/session/history and evidence repositories before request assembly",
        "local recursive key redactor then OpenAI sanitize_structured; opaque payload strings survive",
        "history last 10; evidence builder bounded; question/model content has model validation but no PH-6C byte envelope",
        "none",
        "none",
        "Copilot question/history already persist as product session messages; provider request is not separately persisted",
        "validated answer/evidence IDs persisted as Copilot message",
        "installation SecretStore openai or groq",
        "OpenAI 60s/2 retries/4000 tokens; Groq 60s/2 retries/no max_tokens",
        "Copilot session/API; output has no permission or execution authority",
    ),
    LlmPurpose(
        "investigation-planner",
        "backend/app/services/investigation_planner.py",
        "generate_investigation_plan",
        ("openai", "groq-direct"),
        "incident/RCA/topology/change/blast/evidence catalog",
        True,
        True,
        False,
        "authorized tenant-scoped incident and supporting repositories before evidence construction",
        "local recursive key redactor then OpenAI sanitize_structured; opaque payload strings survive",
        "evidence list is application bounded; no purpose-specific byte/field envelope; Groq response tokens unbounded",
        "none",
        "none",
        "provider request not persisted",
        "validated plan/steps/evidence IDs persisted",
        "installation SecretStore openai or groq",
        "OpenAI 60s/2 retries/4000 tokens; Groq 60s/2 retries/no max_tokens",
        "investigation plan records/API; responder performs actions manually",
    ),
    LlmPurpose(
        "post-incident-report",
        "backend/app/services/post_incident_report.py",
        "generate_post_incident_report",
        ("openai", "groq-direct"),
        "incident, RCA, resolution/outcome, plan/findings/actions, evidence and responder-authored notes",
        True,
        True,
        True,
        "authorized tenant-scoped incident and report dependencies before evidence construction",
        "local recursive key redactor then OpenAI sanitize_structured; opaque payload strings survive",
        "evidence selection bounded; no purpose-specific byte/field envelope; Groq response tokens unbounded",
        "none",
        "none",
        "provider request not persisted",
        "validated report sections/evidence JSON persisted",
        "installation SecretStore openai or groq",
        "OpenAI 60s/2 retries/4000 tokens; Groq 90s/2 retries/no max_tokens",
        "report record/markdown/API",
    ),
    LlmPurpose(
        "execution-readiness-summary",
        "backend/app/services/execution_readiness.py",
        "build_incident_execution_readiness",
        ("openai",),
        "deterministic readiness assessment and bounded incident/action context",
        False,
        True,
        False,
        "tenant-scoped readiness service inputs",
        "central sanitize_structured",
        "central text max_output_tokens plus service-owned bounded context",
        "none",
        "none",
        "not persisted as provider request",
        "narrative returned as optional non-authoritative field",
        "installation SecretStore openai",
        "OpenAI 60s/2 retries; caller output-token bound",
        "optional explanation only; readiness facts remain deterministic",
    ),
    LlmPurpose(
        "incident-briefing-summary",
        "backend/app/services/incident_briefing.py",
        "build_incident_briefing",
        ("openai",),
        "derived structured briefing sections and warnings",
        False,
        True,
        False,
        "all composed services receive the authorized tenant_id",
        "central sanitize_structured",
        "bounded briefing presentation lists and caller output-token bound",
        "none",
        "none",
        "not persisted as provider request",
        "optional ai_summary returned with structured briefing",
        "installation SecretStore openai",
        "OpenAI 60s/2 retries; caller output-token bound",
        "briefing API; cannot alter structured facts",
    ),
    LlmPurpose(
        "incident-similarity-summary",
        "backend/app/services/incident_similarity.py",
        "build_historical_incident_intelligence",
        ("openai",),
        "deterministic current/similar incident comparison facts",
        False,
        True,
        False,
        "tenant-scoped historical candidate query before summarization",
        "central sanitize_structured",
        "bounded similar-incident set and caller output-token bound",
        "none",
        "none",
        "not persisted as provider request",
        "optional explanation returned in historical intelligence",
        "installation SecretStore openai",
        "OpenAI 60s/2 retries; caller output-token bound",
        "historical context; deterministic similarity score remains authoritative",
    ),
    LlmPurpose(
        "response-intelligence-summary",
        "backend/app/services/response_intelligence.py",
        "build_incident_response_intelligence",
        ("openai",),
        "deterministic response action and historical-support facts",
        False,
        True,
        False,
        "tenant-scoped response/history services before summarization",
        "central sanitize_structured",
        "bounded action/history lists and caller output-token bound",
        "none",
        "none",
        "not persisted as provider request",
        "optional narrative returned; actions remain deterministic",
        "installation SecretStore openai",
        "OpenAI 60s/2 retries; caller output-token bound",
        "response intelligence API/briefing",
    ),
)


EXTERNAL_DATA_SINKS = (
    ExternalDataSink("server-database", "installation datastore", (SERVER,), frozenset({TENANT_META, STRUCTURED, RAW, SECRET}), "database URL authority"),
    ExternalDataSink("server-github", "configured GitHub API/artifact provider", (SERVER,), frozenset({CONTROL, TENANT_META, AUTH}), "installation GitHub credential"),
    ExternalDataSink("server-kubernetes", "configured Kubernetes control plane", (SERVER,), frozenset({CONTROL, TENANT_META, AUTH}), "cluster config authority"),
    ExternalDataSink("tenant-webhook", "tenant-selected receiver", (SERVER,), frozenset({CONTROL, TENANT_META, STRUCTURED, RAW, AUTH, SECRET}), "persisted endpoint canonical authority; PH-6B pending"),
    ExternalDataSink("openai", "OpenAI SDK default endpoint", (SERVER,), frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT, RAW, AUTH}), "installation OpenAI credential"),
    ExternalDataSink("groq", "Groq SDK default endpoint", (SERVER,), frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT, RAW, AUTH}), "installation Groq credential"),
    ExternalDataSink("agent-topo", "agent configured Topo server", (AGENT,), frozenset({CONTROL, TENANT_META, STRUCTURED, RAW, AUTH}), "enrolled agent/server authority"),
    ExternalDataSink("agent-aws", "AWS APIs/credential endpoints", (AGENT,), frozenset({CONTROL, TENANT_META, AUTH}), "AWS SDK authority"),
    ExternalDataSink("agent-azure", "Azure APIs/credential endpoints", (AGENT,), frozenset({CONTROL, TENANT_META, AUTH}), "Azure SDK authority"),
    ExternalDataSink("agent-gcp", "Google Cloud APIs/credential endpoints", (AGENT,), frozenset({CONTROL, TENANT_META, AUTH}), "Google SDK authority"),
    ExternalDataSink("agent-kubernetes", "agent configured Kubernetes API", (AGENT,), frozenset({CONTROL, TENANT_META, AUTH}), "cluster config authority"),
    ExternalDataSink("agent-docker", "agent configured Docker daemon", (AGENT,), frozenset({CONTROL, TENANT_META, AUTH}), "Docker config authority"),
    ExternalDataSink("cli-topo", "user selected Topo server", (CLI,), frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT, AUTH}), "local user client authority"),
    ExternalDataSink("browser-topo", "same-origin Topo server", (BROWSER,), frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT, AUTH}), "browser same-origin authority"),
    ExternalDataSink("browser-vercel-analytics", "production Vercel Web Analytics", (BROWSER,), frozenset({PUBLIC, CONTROL, TENANT_META}), "code-mounted browser analytics integration; no product provider credential"),
)


PH6C_RAW_MARKER_REGRESSION_ID = "ph6c-opaque-raw-payload-marker"

# Proposed, not active, purpose-specific PH-6C schemas.  Unknown fields are to
# be omitted; no rich model/dict/model_dump payload is allowed.
PH6C_PROPOSED_ENVELOPES = {
    "LLMIncidentExplanationEnvelope": (
        "incident_id",
        "title",
        "status",
        "severity",
        "observed_at",
        "entity_refs",
        "normalized_signal_codes",
        "normalized_change_facts",
        "causal_hypothesis_claims",
        "topology_relationship_facts",
        "blast_impact_totals",
        "ownership_labels",
        "evidence_claim_refs",
        "warnings",
    ),
    "LLMCopilotEnvelope": (
        "incident_id",
        "question",
        "bounded_conversation_history",
        "incident_facts",
        "causal_hypothesis_claims",
        "topology_relationship_facts",
        "evidence_claim_refs",
    ),
    "LLMInvestigationPlannerEnvelope": (
        "incident_id",
        "incident_facts",
        "root_entity_ref",
        "causal_hypothesis_claims",
        "normalized_change_facts",
        "topology_relationship_facts",
        "blast_impact_totals",
        "existing_validation_checks",
        "evidence_claim_refs",
    ),
    "LLMPostIncidentReportEnvelope": (
        "incident_id",
        "incident_facts",
        "timeline_facts",
        "causal_verdict",
        "resolution_action_facts",
        "outcome_metrics",
        "bounded_responder_notes",
        "evidence_claim_refs",
    ),
}

PH6C_PROPOSED_BOUNDS = {
    "identifier_chars": 256,
    "name_chars": 256,
    "title_chars": 512,
    "normalized_text_chars": 1024,
    "user_question_chars": 4096,
    "responder_note_chars": 4096,
    "conversation_messages": 10,
    "entity_refs": 50,
    "relationship_facts": 100,
    "change_facts": 50,
    "evidence_claim_refs": 100,
    "warnings": 50,
    "total_serialized_bytes": 65536,
}


# Static source coverage sentinels.  A newly introduced network library/source
# must be added to the inventory in the same review.
NETWORK_LIBRARY_MARKERS = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "socket",
    "grpc",
    "websocket",
    "openai",
    "groq",
    "kubernetes",
    "boto3",
    "botocore",
    "azure.identity",
    "azure.mgmt",
    "google.cloud",
    "google.auth",
    "docker",
)


def callsite_counts() -> dict[RuntimeComponent, int]:
    return {
        component: sum(item.component is component for item in EGRESS_CALLSITES)
        for component in RuntimeComponent
    }


def destination_counts() -> dict[DestinationOwnership, int]:
    return {
        ownership: sum(
            item.destination_ownership is ownership
            for item in EGRESS_CALLSITES
            if item.component is SERVER
        )
        for ownership in DestinationOwnership
    }


def risk_counts() -> dict[DestinationRisk, int]:
    return {
        risk: sum(
            item.destination_risk is risk
            for item in EGRESS_CALLSITES
            if item.component is SERVER
        )
        for risk in DestinationRisk
    }
