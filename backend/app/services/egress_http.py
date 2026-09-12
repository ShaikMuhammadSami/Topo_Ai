"""Purpose-specific, address-bound server HTTP egress.

The HTTP request authority always remains the canonical DNS hostname.  The
custom httpcore network backend resolves and validates the complete address
set, then connects the socket to one of those exact validated addresses.  TLS
therefore still receives the canonical hostname from httpcore for SNI and
certificate verification; there is no second hostname resolution.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterable, Iterator
from typing import Any

import httpcore
import httpx

from app.security.egress_policy import (
    EgressErrorCode,
    EgressPolicyError,
    EgressPurpose,
    Resolver,
    ResolvedDestination,
    canonicalize_destination,
    profile_for,
    resolve_destination,
)


_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "connection",
        "cookie",
        "forwarded",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def _is_forbidden_header(name: str) -> bool:
    lowered = name.lower()
    return lowered in _FORBIDDEN_REQUEST_HEADERS or lowered.startswith(
        "x-forwarded-"
    )


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes], maximum_bytes: int) -> None:
        self._stream = stream
        self._maximum_bytes = maximum_bytes
        self._received = 0

    def __iter__(self) -> Iterator[bytes]:
        try:
            for chunk in self._stream:
                self._received += len(chunk)
                if self._received > self._maximum_bytes:
                    self.close()
                    raise EgressPolicyError(EgressErrorCode.RESPONSE_TOO_LARGE)
                yield chunk
        except EgressPolicyError:
            raise
        except httpcore.TimeoutException:
            raise EgressPolicyError(EgressErrorCode.TIMEOUT) from None
        except httpcore.NetworkError:
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE) from None

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if callable(close):
            close()


class AddressBoundNetworkBackend(httpcore.NetworkBackend):
    """Resolve once under policy, then connect only to validated IP values."""

    def __init__(
        self,
        *,
        purpose: EgressPurpose,
        resolver: Resolver,
        github_origin: tuple[str, str, int] | None,
        network_backend: httpcore.NetworkBackend | None = None,
        prepared: ResolvedDestination | None = None,
    ) -> None:
        self._purpose = purpose
        self._resolver = resolver
        self._github_origin = github_origin
        self._network_backend = network_backend or httpcore.SyncBackend()
        self._prepared = prepared

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        try:
            destination = canonicalize_destination(
                f"https://{host}:{port}/",
                purpose=self._purpose,
            )
            if self._prepared is not None:
                if destination.origin != self._prepared.destination.origin:
                    raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
                resolved = self._prepared
            else:
                resolved = resolve_destination(
                    destination,
                    purpose=self._purpose,
                    resolver=self._resolver,
                    github_origin=self._github_origin,
                )
            last_error: Exception | None = None
            for address in resolved.addresses:
                try:
                    return self._network_backend.connect_tcp(
                        host=address,
                        port=port,
                        timeout=timeout,
                        local_address=local_address,
                        socket_options=socket_options,
                    )
                except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                    last_error = exc
            if isinstance(last_error, httpcore.ConnectTimeout):
                raise EgressPolicyError(EgressErrorCode.TIMEOUT) from None
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE)
        except EgressPolicyError:
            raise
        except Exception:
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE) from None

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)


class AddressBoundHTTPTransport(httpx.BaseTransport):
    """HTTPX transport with one immutable purpose and no proxy path."""

    def __init__(
        self,
        *,
        purpose: EgressPurpose,
        resolver: Resolver,
        github_origin: tuple[str, str, int] | None = None,
        network_backend: httpcore.NetworkBackend | None = None,
        prepared: ResolvedDestination | None = None,
    ) -> None:
        self._purpose = purpose
        self._profile = profile_for(purpose)
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise RuntimeError("TLS verification is unavailable")
        self._pool = httpcore.ConnectionPool(
            ssl_context=context,
            max_connections=10,
            max_keepalive_connections=0,
            keepalive_expiry=0.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=AddressBoundNetworkBackend(
                purpose=purpose,
                resolver=resolver,
                github_origin=github_origin,
                network_backend=network_backend,
                prepared=prepared,
            ),
        )
        self._github_origin = github_origin

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method.upper() not in self._profile.methods:
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
        destination = canonicalize_destination(
            str(request.url), purpose=self._purpose
        )
        if self._purpose in {
            EgressPurpose.GITHUB_API_JSON_READ,
            EgressPurpose.GITHUB_SOURCE_CONTENT_READ,
        } and destination.origin != self._github_origin:
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)

        host_values = request.headers.get_list("host")
        if len(host_values) != 1 or host_values[0].lower() != destination.hostname:
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
        if any(
            _is_forbidden_header(name) and name.lower() != "connection"
            for name in request.headers
        ):
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)

        headers = [
            (name, value)
            for name, value in request.headers.raw
            if name.lower() not in {b"accept-encoding", b"connection"}
        ]
        headers.append((b"accept-encoding", b"identity"))
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=headers,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = self._pool.handle_request(core_request)
        except EgressPolicyError as exc:
            if exc.code is EgressErrorCode.TIMEOUT:
                raise httpx.ConnectTimeout("timeout", request=request) from None
            if exc.code is EgressErrorCode.UPSTREAM_UNAVAILABLE:
                raise httpx.ConnectError(
                    "upstream_unavailable", request=request
                ) from None
            raise
        except httpcore.TimeoutException:
            raise EgressPolicyError(EgressErrorCode.TIMEOUT) from None
        except httpcore.NetworkError:
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE) from None
        except httpcore.ProtocolError:
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE) from None

        if 300 <= response.status < 400 and self._purpose in {
            EgressPurpose.GITHUB_API_JSON_READ,
            EgressPurpose.GITHUB_SOURCE_CONTENT_READ,
            EgressPurpose.OPENAI_PROVIDER,
            EgressPurpose.GROQ_PROVIDER,
        }:
            response.close()
            raise EgressPolicyError(EgressErrorCode.REDIRECT_NOT_ALLOWED)

        response_headers = httpx.Headers(response.headers)
        encoding = response_headers.get("content-encoding", "identity").lower()
        if encoding not in {"", "identity"}:
            response.close()
            raise EgressPolicyError(EgressErrorCode.RESPONSE_TOO_LARGE)
        declared = response_headers.get("content-length")
        if (
            self._profile.response_bytes > 0
            and declared
            and declared.isdigit()
            and int(declared) > self._profile.response_bytes
        ):
            response.close()
            raise EgressPolicyError(EgressErrorCode.RESPONSE_TOO_LARGE)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(
                response.stream,
                self._profile.response_bytes
                if self._profile.response_bytes > 0
                else 0,
            ),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


def _client(
    *,
    purpose: EgressPurpose,
    resolver: Resolver,
    github_origin: tuple[str, str, int] | None = None,
    network_backend: httpcore.NetworkBackend | None = None,
    prepared: ResolvedDestination | None = None,
    timeout_seconds: float | None = None,
) -> httpx.Client:
    profile = profile_for(purpose)
    effective_timeout = profile.timeout_seconds
    if timeout_seconds is not None:
        effective_timeout = min(profile.timeout_seconds, max(1.0, timeout_seconds))
    timeout = httpx.Timeout(
        connect=effective_timeout,
        read=effective_timeout,
        write=effective_timeout,
        pool=effective_timeout,
    )
    return httpx.Client(
        transport=AddressBoundHTTPTransport(
            purpose=purpose,
            resolver=resolver,
            github_origin=github_origin,
            network_backend=network_backend,
            prepared=prepared,
        ),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers={"Accept-Encoding": "identity"},
    )


class GitHubEgress:
    """Narrow HTTP boundary for the three supported GitHub read purposes."""

    def __init__(
        self,
        *,
        api_url: str,
        resolver: Resolver,
        network_backend: httpcore.NetworkBackend | None = None,
    ) -> None:
        destination = canonicalize_destination(
            api_url, purpose=EgressPurpose.GITHUB_API_JSON_READ
        )
        self.api_url = destination.url.rstrip("/")
        self.origin = destination.origin
        self._resolver = resolver
        self._network_backend = network_backend

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._bounded_json(
            EgressPurpose.GITHUB_API_JSON_READ,
            url,
            headers=headers,
            params=params,
            maximum_bytes=profile_for(
                EgressPurpose.GITHUB_API_JSON_READ
            ).response_bytes,
        )

    def get_source_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        maximum_bytes: int,
    ) -> Any:
        profile_maximum = profile_for(
            EgressPurpose.GITHUB_SOURCE_CONTENT_READ
        ).response_bytes
        return self._bounded_json(
            EgressPurpose.GITHUB_SOURCE_CONTENT_READ,
            url,
            headers=headers,
            params=params,
            maximum_bytes=min(maximum_bytes, profile_maximum),
        )

    def _bounded_json(
        self,
        purpose: EgressPurpose,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        maximum_bytes: int,
    ) -> Any:
        with _client(
            purpose=purpose,
            resolver=self._resolver,
            github_origin=self.origin,
            network_backend=self._network_backend,
        ) as client:
            with client.stream("GET", url, headers=headers, params=params) as response:
                if 300 <= response.status_code < 400:
                    raise EgressPolicyError(EgressErrorCode.REDIRECT_NOT_ALLOWED)
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > maximum_bytes:
                    raise EgressPolicyError(EgressErrorCode.RESPONSE_TOO_LARGE)
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > maximum_bytes:
                        raise EgressPolicyError(EgressErrorCode.RESPONSE_TOO_LARGE)
        try:
            return httpx.Response(200, content=bytes(payload)).json()
        except ValueError:
            raise EgressPolicyError(EgressErrorCode.UPSTREAM_UNAVAILABLE) from None

    def get_artifact_hop(
        self,
        url: str,
        *,
        headers: dict[str, str],
    ) -> httpx.Response:
        client = _client(
            purpose=EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD,
            resolver=self._resolver,
            github_origin=self.origin,
            network_backend=self._network_backend,
        )
        try:
            request = client.build_request("GET", url, headers=headers)
            response = client.send(request, stream=True)
        except Exception:
            client.close()
            raise
        response.extensions["topo_egress_client"] = client
        return response


def deliver_webhook_once(
    destination: ResolvedDestination,
    *,
    body: str,
    headers: dict[str, str],
    resolver: Resolver,
    network_backend: httpcore.NetworkBackend | None = None,
    timeout_seconds: float = 30.0,
) -> int:
    with _client(
        purpose=EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        resolver=resolver,
        network_backend=network_backend,
        prepared=destination,
        timeout_seconds=timeout_seconds,
    ) as client:
        request = client.build_request(
            "POST", destination.destination.url, content=body, headers=headers
        )
        response = client.send(request, stream=True)
        try:
            return response.status_code
        finally:
            response.close()


def openai_http_client(
    *,
    resolver: Resolver,
    network_backend: httpcore.NetworkBackend | None = None,
) -> httpx.Client:
    return _client(
        purpose=EgressPurpose.OPENAI_PROVIDER,
        resolver=resolver,
        network_backend=network_backend,
    )


def groq_http_client(
    *,
    resolver: Resolver,
    network_backend: httpcore.NetworkBackend | None = None,
) -> httpx.Client:
    return _client(
        purpose=EgressPurpose.GROQ_PROVIDER,
        resolver=resolver,
        network_backend=network_backend,
    )
