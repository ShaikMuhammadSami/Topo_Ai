from __future__ import annotations

import ssl
from collections.abc import Iterable
from types import SimpleNamespace
from pathlib import Path

import httpcore
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import SecurityAuditEventRecord, WebhookEndpointRecord
from app.services.webhook_delivery import create_test_event, deliver_event_to_endpoint
from app.services import llm_client
from app.connectors.github_connector import (
    GitHubConnector,
    GitHubConnectorError,
    GitHubSettings,
)
from app.models.security_audit import SecurityAuditAction, SecurityAuditReason
from app.security.authorization_plan import (
    CRITICAL_OPERATION_PLAN,
    ROUTE_AUTHORIZATION_PLAN,
)
from app.security.authorization_policy import Permission
from app.db.schema_management import script_directory

from app.security.egress_policy import (
    EgressErrorCode,
    EgressPolicyError,
    EgressPurpose,
    canonicalize_destination,
    prepare_destination,
    profile_for,
)
from app.services.egress_http import (
    GitHubEgress,
    deliver_webhook_once,
    groq_http_client,
    openai_http_client,
)
from test_domain_tenant_enforcement import (  # noqa: F401
    sqlite_tenant_app,
    tenant_app,
    two_tenants,
)
from test_tenant_foundation import _bearer, _create_named


PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


class StaticResolver:
    def __init__(self, *answers: tuple[str, ...]) -> None:
        self.answers = list(answers or [(PUBLIC_V4,)])
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class RecordingStream(httpcore.NetworkStream):
    def __init__(self, response: bytes, backend: "RecordingBackend") -> None:
        self._response = [response, b""]
        self.backend = backend
        self.closed = False

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._response.pop(0) if self._response else b""

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.backend.writes.append(bytes(buffer))

    def close(self) -> None:
        self.closed = True

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        self.backend.tls.append((server_hostname, ssl_context))
        return self

    def get_extra_info(self, info: str):
        if info == "ssl_object":
            return SimpleNamespace(selected_alpn_protocol=lambda: "http/1.1")
        if info == "is_readable":
            return False
        return None


class RecordingBackend(httpcore.NetworkBackend):
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.connects: list[tuple[str, int]] = []
        self.writes: list[bytes] = []
        self.tls: list[tuple[str | None, ssl.SSLContext]] = []

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        self.connects.append((host, port))
        return RecordingStream(self.responses.pop(0), self)

    def connect_unix_socket(self, *args, **kwargs):
        raise AssertionError("Unix sockets are not an egress path")


def _response(status: int = 200, body: bytes = b"{}", **headers: str) -> bytes:
    reason = "OK" if status == 200 else "Found"
    values = {"Content-Length": str(len(body)), **headers}
    encoded_headers = b"".join(
        f"{name}: {value}\r\n".encode() for name, value in values.items()
    )
    return (
        f"HTTP/1.1 {status} {reason}\r\n".encode()
        + encoded_headers
        + b"\r\n"
        + body
    )


def _chunked_response(body: bytes) -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        + f"{len(body):x}\r\n".encode()
        + body
        + b"\r\n0\r\n\r\n"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:2375/",
        "https://127.0.0.1/",
        "https://169.254.169.254/",
        "https://10.0.0.5/",
        "https://[::1]/",
        "https://[fc00::1]/",
        "https://[fe80::1]/",
        "https://public.example:8443/",
        "https://user:pass@public.example/",
        "https://public.example/path#fragment",
        "https://2130706433/",
        "https://0177.0.0.1/",
    ],
)
def test_webhook_hostile_url_matrix_is_rejected(url: str) -> None:
    with pytest.raises(EgressPolicyError):
        prepare_destination(
            url,
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=StaticResolver((PUBLIC_V4,)),
        )


def test_hostname_canonicalization_is_structural_and_idna_aware() -> None:
    destination = canonicalize_destination(
        "https://BÜCHER.Example./safe?value=1",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
    )
    assert destination.hostname == "xn--bcher-kva.example"
    assert destination.url == "https://xn--bcher-kva.example/safe?value=1"


@pytest.mark.parametrize(
    "answers",
    [
        ("10.0.0.5",),
        ("169.254.169.254",),
        ("127.0.0.1",),
        ("::1",),
        ("fc00::1",),
        ("fe80::1",),
        (PUBLIC_V4, "10.0.0.5"),
        (PUBLIC_V6, "fc00::1"),
    ],
)
def test_public_dns_policy_rejects_forbidden_or_mixed_answers(
    answers: tuple[str, ...],
) -> None:
    with pytest.raises(
        EgressPolicyError, match=EgressErrorCode.DESTINATION_NOT_ALLOWED.value
    ):
        prepare_destination(
            "https://hooks.example/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=StaticResolver(answers),
        )


def test_actual_socket_target_host_sni_and_certificate_verification_are_preserved() -> None:
    resolver = StaticResolver((PUBLIC_V4,))
    backend = RecordingBackend([_response(body=b'{"ok":true}')])
    egress = GitHubEgress(
        api_url="https://Api.GitHub.Test./",
        resolver=resolver,
        network_backend=backend,
    )
    assert egress.get_json(
        "https://api.github.test/repos/example/repo",
        headers={"Authorization": "Bearer synthetic", "User-Agent": "test"},
    ) == {"ok": True}
    assert resolver.calls == [("api.github.test", 443)]
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert backend.tls[0][0] == "api.github.test"
    assert backend.tls[0][1].verify_mode == ssl.CERT_REQUIRED
    assert backend.tls[0][1].check_hostname is True
    written = b"".join(backend.writes).lower()
    assert b"host: api.github.test\r\n" in written
    assert b"authorization: bearer synthetic\r\n" in written


def test_webhook_post_is_bound_to_prepared_address_and_never_follows_redirect() -> None:
    resolver = StaticResolver((PUBLIC_V4,))
    destination = prepare_destination(
        "https://hooks.example/path",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
    )
    backend = RecordingBackend(
        [_response(status=307, body=b"", Location="https://other.example/")]
    )
    assert deliver_webhook_once(
        destination,
        body='{"safe":true}',
        headers={"Authorization": "Bearer synthetic"},
        resolver=resolver,
        network_backend=backend,
        timeout_seconds=1,
    ) == 307
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert len(backend.tls) == 1
    assert resolver.calls == [("hooks.example", 443)]


def test_dns_rebinding_cannot_trigger_an_independent_second_resolution() -> None:
    resolver = StaticResolver((PUBLIC_V4,), ("127.0.0.1",))
    destination = prepare_destination(
        "https://hooks.example/path",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
    )
    backend = RecordingBackend([_response(status=204, body=b"")])
    assert deliver_webhook_once(
        destination,
        body="{}",
        headers={},
        resolver=resolver,
        network_backend=backend,
    ) == 204
    assert resolver.calls == [("hooks.example", 443)]
    assert backend.connects == [(PUBLIC_V4, 443)]


def test_github_enterprise_private_is_exact_origin_only() -> None:
    resolver = StaticResolver(("10.20.30.40",))
    egress = GitHubEgress(
        api_url="https://github.corp/api/v3",
        resolver=resolver,
        network_backend=RecordingBackend([_response()]),
    )
    assert egress.get_json(
        "https://github.corp/api/v3/repos/example/repo", headers={}
    ) == {}
    with pytest.raises(EgressPolicyError):
        prepare_destination(
            "https://objects.corp/artifact",
            purpose=EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD,
            resolver=StaticResolver(("10.20.30.40",)),
            github_origin=egress.origin,
        )


def test_provider_clients_are_exact_public_https_and_ignore_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    for factory, host in (
        (openai_http_client, "api.openai.com"),
        (groq_http_client, "api.groq.com"),
    ):
        backend = RecordingBackend([_response(body=b'{"ok":true}')])
        with factory(
            resolver=StaticResolver((PUBLIC_V4,)), network_backend=backend
        ) as client:
            response = client.post(
                f"https://{host}/v1/test",
                headers={"Authorization": "Bearer synthetic"},
                json={"input": "safe"},
            )
        assert response.status_code == 200
        assert backend.connects == [(PUBLIC_V4, 443)]
        assert backend.tls[0][0] == host
        assert b"authorization: bearer synthetic" in b"".join(
            backend.writes
        ).lower()


def test_provider_arbitrary_base_url_and_unknown_purpose_fail_closed() -> None:
    client = openai_http_client(resolver=StaticResolver((PUBLIC_V4,)))
    with client, pytest.raises(EgressPolicyError):
        client.post("https://other.example/v1/responses", json={})
    with pytest.raises(EgressPolicyError):
        profile_for("unknown")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factory", "host"),
    (
        (openai_http_client, "api.openai.com"),
        (groq_http_client, "api.groq.com"),
    ),
)
def test_provider_redirect_is_terminal_and_not_replayed(factory, host: str) -> None:
    backend = RecordingBackend(
        [_response(status=307, body=b"", Location="https://other.example/")]
    )
    with factory(
        resolver=StaticResolver((PUBLIC_V4,)), network_backend=backend
    ) as client:
        with pytest.raises(EgressPolicyError, match="redirect_not_allowed"):
            client.post(
                f"https://{host}/v1/test",
                headers={"Authorization": "Bearer synthetic"},
                json={"input": "safe"},
            )
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert b"host: other.example" not in b"".join(backend.writes).lower()


def test_openai_and_groq_sdk_adapters_receive_only_central_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = []
    monkeypatch.setattr(
        llm_client,
        "installation_secret_text",
        lambda provider: f"synthetic-{provider}-key",
    )
    monkeypatch.setattr(
        llm_client,
        "OpenAI",
        lambda **kwargs: observed.append(("openai", kwargs)) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        llm_client,
        "Groq",
        lambda **kwargs: observed.append(("groq", kwargs)) or SimpleNamespace(),
    )
    llm_client._openai_client(resolver=StaticResolver((PUBLIC_V4,)))
    llm_client.create_groq_client(resolver=StaticResolver((PUBLIC_V4,)))
    assert [name for name, _ in observed] == ["openai", "groq"]
    for name, kwargs in observed:
        assert kwargs["api_key"] == f"synthetic-{name}-key"
        assert kwargs["max_retries"] == 2
        assert kwargs["timeout"] == 60.0
        assert isinstance(kwargs["http_client"], httpx.Client)
        assert kwargs["http_client"].follow_redirects is False
        kwargs["http_client"].close()


def test_response_size_is_enforced_before_and_during_consumption() -> None:
    declared = RecordingBackend(
        [_response(body=b"", **{"Content-Length": str(2 * 1024 * 1024 + 1)})]
    )
    egress = GitHubEgress(
        api_url="https://api.github.test",
        resolver=StaticResolver((PUBLIC_V4,)),
        network_backend=declared,
    )
    with pytest.raises(EgressPolicyError, match="response_too_large"):
        egress.get_json("https://api.github.test/repos/x/y", headers={})

    streamed = RecordingBackend(
        [_chunked_response(b"x" * (2 * 1024 * 1024 + 1))]
    )
    egress = GitHubEgress(
        api_url="https://api.github.test",
        resolver=StaticResolver((PUBLIC_V4,)),
        network_backend=streamed,
    )
    with pytest.raises(EgressPolicyError, match="response_too_large"):
        egress.get_json("https://api.github.test/repos/x/y", headers={})


def test_network_errors_are_bounded_and_contain_no_target_or_secret() -> None:
    marker = "synthetic-secret-marker"

    class ExplodingResolver:
        def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
            raise RuntimeError(f"{marker} 10.0.0.8")

    with pytest.raises(EgressPolicyError) as captured:
        prepare_destination(
            "https://hooks.example/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=ExplodingResolver(),
        )
    assert marker not in str(captured.value)
    assert "10.0.0.8" not in str(captured.value)


def test_webhook_origin_change_requires_rotate_but_path_change_does_not(
    two_tenants,
) -> None:
    client, factory, tokens, tenant_id, _ = two_tenants
    created = client.post(
        "/api/v1/integrations/webhooks",
        headers=_bearer(tokens["bootstrap"], tenant_id),
        json={"name": "PH-6B", "url": "https://hooks.example/one"},
    )
    assert created.status_code == 201, created.text
    webhook_id = created.json()["webhook_id"]
    manage = _create_named(
        client,
        tokens["bootstrap"],
        caller_type="service_api",
        subject="service:ph6b-manage",
        roles=["admin"],
        tenant_id=tenant_id,
        permissions=["integration.manage"],
    )
    manage_headers = _bearer(manage["api_credential"])
    path = client.patch(
        f"/api/v1/integrations/webhooks/{webhook_id}",
        headers=manage_headers,
        json={"url": "https://hooks.example/two"},
    )
    assert path.status_code == 200, path.text
    denied = client.patch(
        f"/api/v1/integrations/webhooks/{webhook_id}",
        headers=manage_headers,
        json={"url": "https://other.example/two"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["required_permissions"] == [
        "credential.rotate",
        "integration.manage",
    ]
    allowed = client.patch(
        f"/api/v1/integrations/webhooks/{webhook_id}",
        headers=_bearer(tokens["bootstrap"], tenant_id),
        json={"url": "https://other.example/two"},
    )
    assert allowed.status_code == 200, allowed.text
    with factory() as session:
        events = session.scalars(
            select(SecurityAuditEventRecord).where(
                SecurityAuditEventRecord.action == "webhook_endpoint.updated",
                SecurityAuditEventRecord.resource_id == webhook_id,
            )
        ).all()
    assert [event.permissions_json for event in events[-2:]] == [
        '["integration.manage"]',
        '["credential.rotate","integration.manage"]',
    ]

    blocked_resolver = StaticResolver(("10.0.0.8",))
    client.app.state.egress_resolver = blocked_resolver
    under_authorized = client.patch(
        f"/api/v1/integrations/webhooks/{webhook_id}",
        headers=manage_headers,
        json={"url": "https://blocked.example.com/two"},
    )
    assert under_authorized.status_code == 403
    assert blocked_resolver.calls == []

    egress_denied = client.patch(
        f"/api/v1/integrations/webhooks/{webhook_id}",
        headers=_bearer(tokens["bootstrap"], tenant_id),
        json={"url": "https://blocked.example.com/two"},
    )
    assert egress_denied.status_code == 400
    assert egress_denied.json()["detail"] == "destination_not_allowed"
    assert blocked_resolver.calls == [("blocked.example.com", 443)]


def _endpoint(url: str, *, attempts: int = 1) -> WebhookEndpointRecord:
    return WebhookEndpointRecord(
        webhook_id="webhook:ph6b",
        name="PH-6B",
        url=url,
        event_types_json='["test"]',
        signing_secret_ref="secret:" + ("a" * 36),
        protected_headers_secret_ref="secret:" + ("b" * 36),
        protected_header_names_json='["Authorization"]',
        active=True,
        timeout_seconds=1,
        max_attempts=attempts,
        created_at="2026-09-10T00:00:00+00:00",
        updated_at="2026-09-10T00:00:00+00:00",
    )


def test_blocked_webhook_destination_is_rejected_before_secret_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "app.services.webhook_delivery.load_webhook_secrets",
        lambda *args, **kwargs: pytest.fail(
            "blocked destination decrypted a credential"
        ),
    )

    try:
        with Session(engine) as session:
            endpoint = _endpoint("https://private.example/path")
            endpoint.signing_secret_ref = None
            endpoint.protected_headers_secret_ref = None
            endpoint.tenant_id = "tenant:11111111-1111-4111-8111-111111111111"
            session.add(endpoint)
            session.commit()
            result = deliver_event_to_endpoint(
                session,
                endpoint,
                create_test_event(endpoint.webhook_id, "blocked"),
                tenant_id="tenant:11111111-1111-4111-8111-111111111111",
                secret_store=SimpleNamespace(),
                resolver=StaticResolver(("10.0.0.8",)),
            )
        assert result.status.value == "failed"
        assert result.error_message == "Webhook transport failed (destination_not_allowed)."
    finally:
        engine.dispose()


def test_webhook_retry_re_resolves_and_denies_rebound_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    resolver = StaticResolver((PUBLIC_V4,), ("127.0.0.1",))
    dispatches = []

    def first_fails(destination, **kwargs):
        dispatches.append(destination.addresses)
        raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE)

    monkeypatch.setattr(
        "app.services.webhook_delivery.deliver_webhook_once", first_fails
    )
    monkeypatch.setattr("app.services.webhook_delivery.time.sleep", lambda _: None)
    try:
        with Session(engine) as session:
            endpoint = _endpoint("https://hooks.example/path", attempts=2)
            endpoint.signing_secret_ref = None
            endpoint.protected_headers_secret_ref = None
            endpoint.tenant_id = "tenant:11111111-1111-4111-8111-111111111111"
            session.add(endpoint)
            session.commit()
            result = deliver_event_to_endpoint(
                session,
                endpoint,
                create_test_event(endpoint.webhook_id, "retry"),
                tenant_id="tenant:11111111-1111-4111-8111-111111111111",
                secret_store=SimpleNamespace(),
                resolver=resolver,
            )
        assert result.status.value == "failed"
        assert result.attempt_count == 2
        assert dispatches == [(PUBLIC_V4,)]
        assert resolver.calls == [
            ("hooks.example", 443),
            ("hooks.example", 443),
        ]
    finally:
        engine.dispose()


def test_webhook_redirect_is_terminal_and_body_is_not_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    dispatches = []
    monkeypatch.setattr(
        "app.services.webhook_delivery.deliver_webhook_once",
        lambda destination, **kwargs: dispatches.append(kwargs) or 307,
    )
    try:
        with Session(engine) as session:
            endpoint = _endpoint("https://hooks.example/path", attempts=3)
            endpoint.signing_secret_ref = None
            endpoint.protected_headers_secret_ref = None
            endpoint.tenant_id = "tenant:11111111-1111-4111-8111-111111111111"
            session.add(endpoint)
            session.commit()
            result = deliver_event_to_endpoint(
                session,
                endpoint,
                create_test_event(endpoint.webhook_id, "redirect"),
                tenant_id="tenant:11111111-1111-4111-8111-111111111111",
                secret_store=SimpleNamespace(),
                resolver=StaticResolver((PUBLIC_V4,)),
            )
        assert result.attempt_count == 1
        assert result.response_status == 307
        assert len(dispatches) == 1
    finally:
        engine.dispose()


def test_artifact_redirect_validates_every_hop_and_strips_cross_origin_bearer() -> None:
    marker = "github_pat_synthetic_ph6b"
    backend = RecordingBackend(
        [
            _response(
                status=302,
                body=b"",
                Location="https://objects.example/artifact.zip?signature=opaque",
            ),
            _response(body=b"zip"),
        ]
    )
    resolver = StaticResolver((PUBLIC_V4,))
    settings = GitHubSettings(
        owner="example",
        repository="repo",
        token=marker,
        api_url="https://api.github.test",
        api_version="test",
        timeout_seconds=1,
        commit_limit=1,
    )
    egress = GitHubEgress(
        api_url=settings.api_url,
        resolver=resolver,
        network_backend=backend,
    )
    assert GitHubConnector(settings, egress=egress).download_actions_artifact(1) == b"zip"
    wire = b"".join(backend.writes).lower()
    assert wire.count(b"authorization: bearer ") == 1
    assert b"host: api.github.test\r\n" in wire
    assert b"host: objects.example\r\n" in wire
    assert resolver.calls == [
        ("api.github.test", 443),
        ("objects.example", 443),
    ]


def test_artifact_cross_origin_private_redirect_is_denied_before_second_connect() -> None:
    marker = "github_pat_synthetic_ph6b"
    backend = RecordingBackend(
        [
            _response(
                status=302,
                body=b"",
                Location="https://objects.example/artifact.zip?signature=opaque",
            )
        ]
    )
    resolver = StaticResolver((PUBLIC_V4,), ("169.254.169.254",))
    settings = GitHubSettings(
        owner="example",
        repository="repo",
        token=marker,
        api_url="https://api.github.test",
        api_version="test",
        timeout_seconds=1,
        commit_limit=1,
    )
    egress = GitHubEgress(
        api_url=settings.api_url,
        resolver=resolver,
        network_backend=backend,
    )
    with pytest.raises(GitHubConnectorError) as captured:
        GitHubConnector(settings, egress=egress).download_actions_artifact(1)
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert marker not in str(captured.value)
    assert "169.254.169.254" not in str(captured.value)


@pytest.mark.parametrize(
    "location",
    (
        "http://objects.example/artifact.zip",
        "https://objects.example:8443/artifact.zip",
        "https://user:password@objects.example/artifact.zip",
        "https://objects.example/artifact.zip#fragment",
    ),
)
def test_artifact_unsafe_redirect_is_denied_before_second_connect(
    location: str,
) -> None:
    backend = RecordingBackend(
        [_response(status=302, body=b"", Location=location)]
    )
    connector = GitHubConnector(
        GitHubSettings(
            owner="example",
            repository="repo",
            token="github_pat_synthetic_ph6b",
            api_url="https://api.github.test",
            api_version="test",
            timeout_seconds=1,
            commit_limit=1,
        ),
        egress=GitHubEgress(
            api_url="https://api.github.test",
            resolver=StaticResolver((PUBLIC_V4,)),
            network_backend=backend,
        ),
    )
    with pytest.raises(GitHubConnectorError):
        connector.download_actions_artifact(1)
    assert backend.connects == [(PUBLIC_V4, 443)]


def test_artifact_hop_limit_stops_before_a_fifth_dispatch() -> None:
    backend = RecordingBackend(
        [
            _response(
                status=302,
                body=b"",
                Location=f"https://objects.example/artifact-{index}.zip",
            )
            for index in range(4)
        ]
    )
    connector = GitHubConnector(
        GitHubSettings(
            owner="example",
            repository="repo",
            token="github_pat_synthetic_ph6b",
            api_url="https://api.github.test",
            api_version="test",
            timeout_seconds=1,
            commit_limit=1,
        ),
        egress=GitHubEgress(
            api_url="https://api.github.test",
            resolver=StaticResolver((PUBLIC_V4,)),
            network_backend=backend,
        ),
    )
    with pytest.raises(GitHubConnectorError, match="redirect limit"):
        connector.download_actions_artifact(1)
    assert len(backend.connects) == 4


def test_server_http_dispatch_is_complete_and_has_no_bypass_flags() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    sources = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
    }
    direct_httpx = {
        name
        for name, source in sources.items()
        if "httpx.Client(" in source
    }
    assert direct_httpx == {"services/egress_http.py"}
    assert {
        name for name, source in sources.items() if "Groq(" in source
    } == {"services/llm_client.py"}
    assert {
        name for name, source in sources.items() if "OpenAI(" in source
    } == {"services/llm_client.py"}
    joined = "\n".join(sources.values()).lower()
    for flag in (
        "skip_ssrf",
        "bypass_egress",
        "allow_private",
        "allow_any_host",
        "disable_dns_check",
    ):
        assert flag not in joined


def test_ph6b_preserves_route_operation_permission_audit_and_schema_counts() -> None:
    assert len(ROUTE_AUTHORIZATION_PLAN) == 143
    assert len(CRITICAL_OPERATION_PLAN) == 98
    assert len(Permission) == 18
    assert len(SecurityAuditAction) == 33
    assert len(SecurityAuditReason) == 11
    assert len(Base.metadata.tables) == 50
    assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
    assert script_directory().get_heads() == ["0015_security_audit"]
