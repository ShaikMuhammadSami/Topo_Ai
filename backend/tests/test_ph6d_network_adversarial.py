"""PH-6D adversarial network, DNS, redirect and credential acceptance."""

from __future__ import annotations

import ssl

import pytest

from app.connectors.github_connector import (
    GitHubConnector,
    GitHubConnectorError,
    GitHubSettings,
)
from app.security.egress_policy import (
    AddressPolicy,
    EgressErrorCode,
    EgressPolicyError,
    EgressPurpose,
    canonicalize_destination,
    prepare_destination,
    validate_addresses,
)
from app.services.egress_http import (
    GitHubEgress,
    deliver_webhook_once,
    groq_http_client,
    openai_http_client,
)
from test_ph6b_egress_policy import (
    PUBLIC_V4,
    PUBLIC_V6,
    RecordingBackend,
    StaticResolver,
    _chunked_response,
    _response,
)


@pytest.mark.parametrize(
    "url",
    (
        "https://127.0.0.1/",
        "https://127.1/",
        "https://127.255.255.255/",
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://10.0.0.1/",
        "https://172.16.0.1/",
        "https://172.31.255.254/",
        "https://192.168.0.1/",
        "https://[fc00::1]/",
        "https://[fd00::1]/",
        "https://[fe80::1]/",
        "https://169.254.1.1/",
        "https://169.254.169.254/",
        "https://[::ffff:169.254.169.254]/",
        "https://0.0.0.0/",
        "https://[::]/",
        "https://224.0.0.1/",
        "https://255.255.255.255/",
        "https://93.184.216.34/",
        "https://2130706433/",
        "https://0x7f000001/",
        "https://017700000001/",
        "https://0177.0.0.1/",
        "https://127.0.1/",
    ),
)
def test_tenant_webhook_rejects_ip_and_ambiguous_host_matrix(url: str) -> None:
    with pytest.raises(EgressPolicyError):
        prepare_destination(
            url,
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=StaticResolver((PUBLIC_V4,)),
        )


@pytest.mark.parametrize(
    "answers",
    (
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("172.16.0.1",),
        ("172.31.255.254",),
        ("192.168.0.1",),
        ("fc00::1",),
        ("fd00::1",),
        ("fe80::1",),
        ("169.254.1.1",),
        ("169.254.169.254",),
        ("0.0.0.0",),
        ("::",),
        ("224.0.0.1",),
        ("ff02::1",),
        ("192.0.2.1",),
        ("::ffff:127.0.0.1",),
        ("::ffff:169.254.169.254",),
    ),
)
def test_public_policy_rejects_forbidden_final_dns_results(
    answers: tuple[str, ...],
) -> None:
    with pytest.raises(
        EgressPolicyError,
        match=EgressErrorCode.DESTINATION_NOT_ALLOWED.value,
    ):
        prepare_destination(
            "https://hooks.example/event",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=StaticResolver(answers),
        )


@pytest.mark.parametrize(
    "answers",
    (
        (PUBLIC_V4, "10.0.0.1"),
        (PUBLIC_V6, "fc00::1"),
        (PUBLIC_V4, "169.254.1.1"),
        (PUBLIC_V4, "169.254.169.254"),
    ),
)
def test_mixed_public_forbidden_dns_fails_the_entire_set(
    answers: tuple[str, ...],
) -> None:
    with pytest.raises(EgressPolicyError):
        prepare_destination(
            "https://hooks.example/event",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=StaticResolver(answers),
        )


@pytest.mark.parametrize("scheme", ("http", "ftp", "file", "gopher", "data", "ws"))
def test_webhook_rejects_non_https_schemes(scheme: str) -> None:
    with pytest.raises(EgressPolicyError):
        canonicalize_destination(
            f"{scheme}://hooks.example/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        )


@pytest.mark.parametrize("port", (80, 22, 2375, 5432, 6379, 8443))
def test_webhook_rejects_non_443_ports(port: int) -> None:
    with pytest.raises(EgressPolicyError):
        canonicalize_destination(
            f"https://hooks.example:{port}/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        )


def test_webhook_rejects_userinfo_and_canonicalizes_case_dot_and_idna() -> None:
    with pytest.raises(EgressPolicyError):
        canonicalize_destination(
            "https://user:password@hooks.example/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        )
    variants = (
        "https://BÜCHER.Example/path",
        "https://xn--bcher-kva.example./path",
        "https://XN--BCHER-KVA.EXAMPLE/path",
    )
    destinations = tuple(
        canonicalize_destination(
            item,
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        )
        for item in variants
    )
    assert {item.origin for item in destinations} == {
        ("https", "xn--bcher-kva.example", 443)
    }
    assert len({item.url for item in destinations}) == 1


def test_validated_socket_host_sni_certificate_and_single_resolution() -> None:
    resolver = StaticResolver((PUBLIC_V4,), ("127.0.0.1",))
    backend = RecordingBackend([_response(body=b"{}")])
    destination = prepare_destination(
        "https://Hooks.Example./event",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
    )
    assert deliver_webhook_once(
        destination,
        body="{}",
        headers={"X-Test": "safe"},
        resolver=resolver,
        network_backend=backend,
    ) == 200
    assert resolver.calls == [("hooks.example", 443)]
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert backend.tls[0][0] == "hooks.example"
    context = backend.tls[0][1]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert b"host: hooks.example\r\n" in b"".join(backend.writes).lower()


def test_every_new_connection_gets_a_fresh_policy_decision() -> None:
    resolver = StaticResolver((PUBLIC_V4,), ("127.0.0.1",))
    first = prepare_destination(
        "https://hooks.example/event",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
    )
    assert first.addresses == (PUBLIC_V4,)
    with pytest.raises(EgressPolicyError):
        prepare_destination(
            "https://hooks.example/event",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=resolver,
        )
    assert resolver.calls == [
        ("hooks.example", 443),
        ("hooks.example", 443),
    ]


@pytest.mark.parametrize("status", (301, 302, 303, 307, 308))
@pytest.mark.parametrize(
    "location",
    (
        "https://hooks.example/other",
        "https://other.example/path",
        "http://other.example/path",
        "https://10.0.0.1/path",
        "https://169.254.169.254/path",
        "https://other.example:8443/path",
    ),
)
def test_webhook_redirect_matrix_never_dispatches_a_second_request(
    status: int,
    location: str,
) -> None:
    resolver = StaticResolver((PUBLIC_V4,), ("127.0.0.1",))
    destination = prepare_destination(
        "https://hooks.example/event",
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
    )
    backend = RecordingBackend(
        [_response(status=status, body=b"", Location=location)]
    )
    assert deliver_webhook_once(
        destination,
        body='{"bounded":true}',
        headers={"Authorization": "Bearer synthetic"},
        resolver=resolver,
        network_backend=backend,
    ) == status
    assert backend.connects == [(PUBLIC_V4, 443)]
    wire = b"".join(backend.writes)
    assert wire.count(b"POST /event HTTP/1.1") == 1
    assert wire.count(b'{"bounded":true}') == 1
    assert resolver.calls == [("hooks.example", 443)]


def test_hostile_environment_proxies_and_proxy_credentials_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "proxy-password-ph6d"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, f"http://proxy-user:{marker}@127.0.0.1:9999")
    backend = RecordingBackend([_response(body=b"{}")])
    with openai_http_client(
        resolver=StaticResolver((PUBLIC_V4,)), network_backend=backend
    ) as client:
        assert client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer provider-key"},
            json={"input": "safe"},
        ).status_code == 200
    wire = b"".join(backend.writes)
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert marker.encode() not in wire


@pytest.mark.parametrize(
    ("factory", "approved", "other"),
    (
        (openai_http_client, "api.openai.com", "api.groq.com"),
        (groq_http_client, "api.groq.com", "api.openai.com"),
    ),
)
def test_provider_destination_and_credential_swap_fail_before_dispatch(
    factory,
    approved: str,
    other: str,
) -> None:
    backend = RecordingBackend([_response(body=b"{}")])
    with factory(
        resolver=StaticResolver((PUBLIC_V4,)), network_backend=backend
    ) as client:
        with pytest.raises(EgressPolicyError):
            client.post(
                f"https://{other}/v1/test",
                headers={"Authorization": f"Bearer {approved}-credential"},
                json={"input": "safe"},
            )
    assert backend.connects == []
    assert backend.writes == []


@pytest.mark.parametrize("status", (301, 302, 303, 307, 308))
@pytest.mark.parametrize(
    ("factory", "host"),
    (
        (openai_http_client, "api.openai.com"),
        (groq_http_client, "api.groq.com"),
    ),
)
def test_llm_redirects_are_terminal_without_body_or_credential_replay(
    status: int,
    factory,
    host: str,
) -> None:
    backend = RecordingBackend(
        [_response(status=status, body=b"", Location="https://other.example/")]
    )
    with factory(
        resolver=StaticResolver((PUBLIC_V4,)), network_backend=backend
    ) as client:
        with pytest.raises(EgressPolicyError, match="redirect_not_allowed"):
            client.post(
                f"https://{host}/v1/test",
                headers={"Authorization": "Bearer provider-key"},
                json={"marker": "customer-body-ph6d"},
            )
    wire = b"".join(backend.writes)
    assert backend.connects == [(PUBLIC_V4, 443)]
    assert wire.count(b"provider-key") == 1
    assert wire.count(b"customer-body-ph6d") == 1


def test_github_enterprise_private_exception_is_exact_and_nontransferable() -> None:
    for address in ("10.20.30.40", "fd00::10"):
        origin = canonicalize_destination(
            "https://github.corp/api/v3",
            purpose=EgressPurpose.GITHUB_API_JSON_READ,
        ).origin
        resolved = prepare_destination(
            "https://github.corp/api/v3/repos/o/r",
            purpose=EgressPurpose.GITHUB_API_JSON_READ,
            resolver=StaticResolver((address,)),
            github_origin=origin,
        )
        assert resolved.addresses == (address,)
        with pytest.raises(EgressPolicyError):
            prepare_destination(
                "https://objects.corp/artifact",
                purpose=EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD,
                resolver=StaticResolver((address,)),
                github_origin=origin,
            )
    for address in ("127.0.0.1", "169.254.169.254", "fe80::1", "::"):
        with pytest.raises(EgressPolicyError):
            validate_addresses(
                (address,), address_policy=AddressPolicy.GITHUB_INSTALLATION
            )


@pytest.mark.parametrize(
    "location",
    (
        "https://127.0.0.1/object",
        "https://169.254.169.254/object",
        "https://10.0.0.1/object",
        "https://[fd00::1]/object",
        "https://[fe80::1]/object",
        "http://objects.example/object",
        "https://objects.example:8443/object",
        "https://user:password@objects.example/object",
    ),
)
def test_github_forged_artifact_location_never_gets_a_second_connect(
    location: str,
) -> None:
    backend = RecordingBackend([_response(status=302, body=b"", Location=location)])
    connector = GitHubConnector(
        GitHubSettings(
            owner="example",
            repository="repo",
            token="github_pat_synthetic_ph6d",
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


def test_github_source_artifact_and_encoding_response_bounds() -> None:
    source_backend = RecordingBackend(
        [_chunked_response(b"x" * (160 * 1024 + 1))]
    )
    source = GitHubEgress(
        api_url="https://api.github.test",
        resolver=StaticResolver((PUBLIC_V4,)),
        network_backend=source_backend,
    )
    with pytest.raises(EgressPolicyError, match="response_too_large"):
        source.get_source_json(
            "https://api.github.test/repos/o/r/contents/file",
            headers={},
            params=None,
            maximum_bytes=999_999,
        )

    artifact_backend = RecordingBackend(
        [_response(body=b"", **{"Content-Length": str(32 * 1024 * 1024 + 1)})]
    )
    artifact = GitHubEgress(
        api_url="https://api.github.test",
        resolver=StaticResolver((PUBLIC_V4,)),
        network_backend=artifact_backend,
    )
    with pytest.raises(EgressPolicyError, match="response_too_large"):
        artifact.get_artifact_hop(
            "https://objects.example/artifact.zip", headers={}
        )

    encoded_backend = RecordingBackend(
        [_response(body=b"compressed", **{"Content-Encoding": "gzip"})]
    )
    encoded = GitHubEgress(
        api_url="https://api.github.test",
        resolver=StaticResolver((PUBLIC_V4,)),
        network_backend=encoded_backend,
    )
    with pytest.raises(EgressPolicyError, match="response_too_large"):
        encoded.get_json("https://api.github.test/repos/o/r", headers={})


def test_bounded_network_errors_expose_no_target_or_credentials() -> None:
    marker = "signed-or-secret-ph6d"

    class ExplodingResolver:
        def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
            raise RuntimeError(
                f"Bearer {marker} https://10.0.0.8/path?signature={marker}"
            )

    with pytest.raises(EgressPolicyError) as captured:
        prepare_destination(
            "https://hooks.example/path",
            purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
            resolver=ExplodingResolver(),
        )
    rendered = str(captured.value)
    assert rendered == EgressErrorCode.DNS_RESOLUTION_FAILED.value
    assert marker not in rendered
    assert "10.0.0.8" not in rendered
