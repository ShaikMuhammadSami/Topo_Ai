"""Executable PH-6B server egress policy.

The registry in :mod:`app.security.egress_inventory` remains the historical
PH-6A inventory.  This module is the small, fail-closed runtime policy used by
the central HTTP transport.  Application callers never select a purpose from
request data.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit


class EgressPurpose(StrEnum):
    GITHUB_API_JSON_READ = "GITHUB_API_JSON_READ"
    GITHUB_SOURCE_CONTENT_READ = "GITHUB_SOURCE_CONTENT_READ"
    GITHUB_ARTIFACT_DOWNLOAD = "GITHUB_ARTIFACT_DOWNLOAD"
    TENANT_WEBHOOK_DELIVERY = "TENANT_WEBHOOK_DELIVERY"
    OPENAI_PROVIDER = "OPENAI_PROVIDER"
    GROQ_PROVIDER = "GROQ_PROVIDER"


class EgressErrorCode(StrEnum):
    DESTINATION_INVALID = "destination_invalid"
    DESTINATION_NOT_ALLOWED = "destination_not_allowed"
    DNS_RESOLUTION_FAILED = "dns_resolution_failed"
    REDIRECT_NOT_ALLOWED = "redirect_not_allowed"
    TLS_FAILURE = "tls_failure"
    TIMEOUT = "timeout"
    RESPONSE_TOO_LARGE = "response_too_large"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"


class EgressPolicyError(RuntimeError):
    """Bounded semantic error that never contains a URL, address, or secret."""

    def __init__(self, code: EgressErrorCode):
        self.code = code
        super().__init__(code.value)


class AddressPolicy(StrEnum):
    PUBLIC = "public"
    GITHUB_INSTALLATION = "github_installation"


@dataclass(frozen=True)
class EgressProfile:
    purpose: EgressPurpose
    methods: frozenset[str]
    address_policy: AddressPolicy
    response_bytes: int
    timeout_seconds: float
    sdk_retries: int = 0


@dataclass(frozen=True)
class CanonicalDestination:
    url: str
    scheme: str
    hostname: str
    port: int
    path: str
    query: str

    @property
    def origin(self) -> tuple[str, str, int]:
        return self.scheme, self.hostname, self.port


@dataclass(frozen=True)
class ResolvedDestination:
    destination: CanonicalDestination
    addresses: tuple[str, ...]


class Resolver(Protocol):
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


MAX_DNS_ADDRESSES = 16
GITHUB_JSON_RESPONSE_BYTES = 2 * 1024 * 1024
GITHUB_SOURCE_RESPONSE_BYTES = 160 * 1024
GITHUB_ARTIFACT_RESPONSE_BYTES = 32 * 1024 * 1024
LLM_RESPONSE_BYTES = 8 * 1024 * 1024

EGRESS_PROFILES = {
    EgressPurpose.GITHUB_API_JSON_READ: EgressProfile(
        EgressPurpose.GITHUB_API_JSON_READ,
        frozenset({"GET"}),
        AddressPolicy.GITHUB_INSTALLATION,
        GITHUB_JSON_RESPONSE_BYTES,
        20.0,
    ),
    EgressPurpose.GITHUB_SOURCE_CONTENT_READ: EgressProfile(
        EgressPurpose.GITHUB_SOURCE_CONTENT_READ,
        frozenset({"GET"}),
        AddressPolicy.GITHUB_INSTALLATION,
        GITHUB_SOURCE_RESPONSE_BYTES,
        20.0,
    ),
    EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD: EgressProfile(
        EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD,
        frozenset({"GET"}),
        AddressPolicy.PUBLIC,
        GITHUB_ARTIFACT_RESPONSE_BYTES,
        20.0,
    ),
    EgressPurpose.TENANT_WEBHOOK_DELIVERY: EgressProfile(
        EgressPurpose.TENANT_WEBHOOK_DELIVERY,
        frozenset({"POST"}),
        AddressPolicy.PUBLIC,
        0,
        30.0,
    ),
    EgressPurpose.OPENAI_PROVIDER: EgressProfile(
        EgressPurpose.OPENAI_PROVIDER,
        frozenset({"POST"}),
        AddressPolicy.PUBLIC,
        LLM_RESPONSE_BYTES,
        60.0,
        sdk_retries=2,
    ),
    EgressPurpose.GROQ_PROVIDER: EgressProfile(
        EgressPurpose.GROQ_PROVIDER,
        frozenset({"POST"}),
        AddressPolicy.PUBLIC,
        LLM_RESPONSE_BYTES,
        60.0,
        sdk_retries=2,
    ),
}

_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_AMBIGUOUS_IP = re.compile(
    r"(?i)(?:[0-9]+|0x[0-9a-f]+|(?:[0-9a-fx]+\.)+[0-9a-fx]+)\Z"
)
_CREDENTIAL_QUERY_KEYS = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "key",
        "password",
        "secret",
        "signature",
        "sig",
        "token",
    }
)
_CREDENTIAL_PATH = re.compile(
    r"(?i)(?:^|/)(?:access[-_]?token|api[-_]?key|authorization|credential|"
    r"password|secret|signature|token)(?:/|=|:|$)|"
    r"(?:sk-|gsk_|ghp_|github_pat_|topo_(?:api|agent|enroll)_)[a-z0-9._~-]{8,}"
)
_RFC1918 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
_IPV6_ULA = ipaddress.ip_network("fc00::/7")
_PROVIDER_HOSTS = {
    EgressPurpose.OPENAI_PROVIDER: "api.openai.com",
    EgressPurpose.GROQ_PROVIDER: "api.groq.com",
}


class SystemResolver:
    """One bounded OS A/AAAA resolution with no authorization cache."""

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            answers = socket.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
            values = {
                str(ipaddress.ip_address(item[4][0]))
                for item in answers
                if item[0] in {socket.AF_INET, socket.AF_INET6}
            }
        except (OSError, TypeError, ValueError):
            raise EgressPolicyError(EgressErrorCode.DNS_RESOLUTION_FAILED) from None
        ordered = tuple(
            sorted(values, key=lambda value: (ipaddress.ip_address(value).version, int(ipaddress.ip_address(value))))
        )
        if not ordered or len(ordered) > MAX_DNS_ADDRESSES:
            raise EgressPolicyError(EgressErrorCode.DNS_RESOLUTION_FAILED)
        return ordered


def profile_for(purpose: EgressPurpose) -> EgressProfile:
    try:
        return EGRESS_PROFILES[EgressPurpose(purpose)]
    except (KeyError, TypeError, ValueError):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED) from None


def _canonical_hostname(hostname: str) -> str:
    value = hostname.rstrip(".")
    if not value or len(value) > 253:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID)
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    if _AMBIGUOUS_IP.fullmatch(value):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    try:
        ascii_value = value.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID) from None
    labels = ascii_value.split(".")
    if any(not _DNS_LABEL.fullmatch(label) for label in labels):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID)
    return ascii_value


def canonicalize_destination(
    value: str,
    *,
    purpose: EgressPurpose,
) -> CanonicalDestination:
    profile = profile_for(purpose)
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID)
        port = parsed.port or 443
    except EgressPolicyError:
        raise
    except (TypeError, ValueError):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID) from None
    if port != 443:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    hostname = _canonical_hostname(parsed.hostname)
    if profile.address_policy is AddressPolicy.PUBLIC and "." not in hostname:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    if purpose in _PROVIDER_HOSTS and hostname != _PROVIDER_HOSTS[purpose]:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    path = parsed.path or "/"
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EgressPolicyError(EgressErrorCode.DESTINATION_INVALID)
    if purpose is EgressPurpose.TENANT_WEBHOOK_DELIVERY:
        for name, _ in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            if normalized in _CREDENTIAL_QUERY_KEYS:
                raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
        if _CREDENTIAL_PATH.search(unquote(path)):
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    canonical_url = urlunsplit(("https", hostname, path, parsed.query, ""))
    return CanonicalDestination(
        url=canonical_url,
        scheme="https",
        hostname=hostname,
        port=443,
        path=path,
        query=parsed.query,
    )


def _address_kind(value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    # ``is_global`` is not a sufficient egress allow decision: Python treats
    # multicast address space as globally scoped.  Special-purpose addresses
    # are never valid external HTTP socket targets even when globally scoped.
    if (
        value.is_loopback
        or value.is_link_local
        or value.is_multicast
        or value.is_unspecified
        or value.is_reserved
    ):
        return "forbidden"
    if value.is_global:
        return "global"
    if isinstance(value, ipaddress.IPv4Address) and any(value in network for network in _RFC1918):
        return "private"
    if isinstance(value, ipaddress.IPv6Address) and value in _IPV6_ULA:
        return "private"
    return "forbidden"


def validate_addresses(
    addresses: tuple[str, ...],
    *,
    address_policy: AddressPolicy,
) -> tuple[str, ...]:
    if not addresses or len(addresses) > MAX_DNS_ADDRESSES:
        raise EgressPolicyError(EgressErrorCode.DNS_RESOLUTION_FAILED)
    canonical: set[str] = set()
    kinds: set[str] = set()
    try:
        for address in addresses:
            parsed = ipaddress.ip_address(address)
            if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
                raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
            kind = _address_kind(parsed)
            if kind == "forbidden":
                raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
            if address_policy is AddressPolicy.PUBLIC and kind != "global":
                raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
            canonical.add(str(parsed))
            kinds.add(kind)
    except EgressPolicyError:
        raise
    except (TypeError, ValueError):
        raise EgressPolicyError(EgressErrorCode.DNS_RESOLUTION_FAILED) from None
    if len(kinds) != 1:
        raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    return tuple(
        sorted(canonical, key=lambda value: (ipaddress.ip_address(value).version, int(ipaddress.ip_address(value))))
    )


def resolve_destination(
    destination: CanonicalDestination,
    *,
    purpose: EgressPurpose,
    resolver: Resolver,
    github_origin: tuple[str, str, int] | None = None,
) -> ResolvedDestination:
    profile = profile_for(purpose)
    address_policy = profile.address_policy
    if purpose in {
        EgressPurpose.GITHUB_API_JSON_READ,
        EgressPurpose.GITHUB_SOURCE_CONTENT_READ,
    }:
        if github_origin is None or destination.origin != github_origin:
            raise EgressPolicyError(EgressErrorCode.DESTINATION_NOT_ALLOWED)
    elif purpose is EgressPurpose.GITHUB_ARTIFACT_DOWNLOAD:
        address_policy = (
            AddressPolicy.GITHUB_INSTALLATION
            if github_origin is not None and destination.origin == github_origin
            else AddressPolicy.PUBLIC
        )
    try:
        raw_addresses = resolver.resolve(destination.hostname, destination.port)
    except EgressPolicyError:
        raise
    except Exception:
        raise EgressPolicyError(EgressErrorCode.DNS_RESOLUTION_FAILED) from None
    addresses = validate_addresses(raw_addresses, address_policy=address_policy)
    return ResolvedDestination(destination=destination, addresses=addresses)


def prepare_destination(
    value: str,
    *,
    purpose: EgressPurpose,
    resolver: Resolver | None = None,
    github_origin: tuple[str, str, int] | None = None,
) -> ResolvedDestination:
    destination = canonicalize_destination(value, purpose=purpose)
    return resolve_destination(
        destination,
        purpose=purpose,
        resolver=resolver or SystemResolver(),
        github_origin=github_origin,
    )
