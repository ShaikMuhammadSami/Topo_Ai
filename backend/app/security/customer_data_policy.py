"""Code-owned customer-data policy for current external sinks.

This module answers only what data classes may leave through an already
authorized, tenant-scoped and PH-6B-approved destination.  It grants no
network, tenant, credential, or product authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.security.egress_inventory import CustomerDataClass
from app.security.secret_redaction import REDACTED, safe_text


class ExternalDataSink(StrEnum):
    GITHUB = "GITHUB"
    TENANT_WEBHOOK = "TENANT_WEBHOOK"
    OPENAI = "OPENAI"
    GROQ = "GROQ"
    VERCEL_ANALYTICS = "VERCEL_ANALYTICS"


@dataclass(frozen=True, slots=True)
class ExternalDataSinkPolicy:
    sink: ExternalDataSink
    content_classes: frozenset[CustomerDataClass]
    transport_only_classes: frozenset[CustomerDataClass] = frozenset()
    enabled_for_authenticated_product: bool = True


PUBLIC = CustomerDataClass.PUBLIC_SYSTEM_DATA
CONTROL = CustomerDataClass.TOPO_CONTROL_METADATA
TENANT_META = CustomerDataClass.TENANT_OPERATIONAL_METADATA
STRUCTURED = CustomerDataClass.CUSTOMER_STRUCTURED_OPERATIONAL_DATA
USER_TEXT = CustomerDataClass.CUSTOMER_USER_AUTHORED_CONTENT
AUTH = CustomerDataClass.AUTHENTICATION_SECRET
SECRET = CustomerDataClass.SECRET_MATERIAL


EXTERNAL_DATA_SINK_POLICIES = {
    ExternalDataSink.GITHUB: ExternalDataSinkPolicy(
        ExternalDataSink.GITHUB,
        frozenset({PUBLIC, CONTROL, TENANT_META}),
        frozenset({AUTH}),
    ),
    ExternalDataSink.TENANT_WEBHOOK: ExternalDataSinkPolicy(
        ExternalDataSink.TENANT_WEBHOOK,
        frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT}),
        frozenset({AUTH, SECRET}),
    ),
    ExternalDataSink.OPENAI: ExternalDataSinkPolicy(
        ExternalDataSink.OPENAI,
        frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT}),
        frozenset({AUTH}),
    ),
    ExternalDataSink.GROQ: ExternalDataSinkPolicy(
        ExternalDataSink.GROQ,
        frozenset({CONTROL, TENANT_META, STRUCTURED, USER_TEXT}),
        frozenset({AUTH}),
    ),
    ExternalDataSink.VERCEL_ANALYTICS: ExternalDataSinkPolicy(
        ExternalDataSink.VERCEL_ANALYTICS,
        frozenset({PUBLIC}),
        enabled_for_authenticated_product=False,
    ),
}


class CustomerDataPolicyError(ValueError):
    """Bounded external-data-policy failure without customer content."""


def policy_for_sink(sink: ExternalDataSink) -> ExternalDataSinkPolicy:
    if not isinstance(sink, ExternalDataSink):
        raise CustomerDataPolicyError("external_sink_not_allowed")
    try:
        return EXTERNAL_DATA_SINK_POLICIES[sink]
    except KeyError:
        raise CustomerDataPolicyError("external_sink_not_allowed") from None


def require_content_classes(
    sink: ExternalDataSink,
    classes: frozenset[CustomerDataClass],
) -> None:
    policy = policy_for_sink(sink)
    if not classes.issubset(policy.content_classes):
        raise CustomerDataPolicyError("customer_data_class_not_allowed")


_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?"
    r"-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[^\r\n]*",
    re.IGNORECASE,
)
_TRUNCATED = "[TRUNCATED]"


def scrub_outbound_text(value: str, *, maximum: int) -> str:
    """Scrub admitted free text; this never makes raw payloads admissible."""
    if not isinstance(value, str):
        raise CustomerDataPolicyError("customer_text_invalid")
    candidate = _PRIVATE_KEY.sub(REDACTED, value)
    candidate = _GENERIC_PEM_PRIVATE_KEY.sub(REDACTED, candidate)
    # The existing PH-4 primitive covers Authorization/Basic material,
    # provider tokens, assignments, database URLs and credential URLs.
    bounded_source = safe_text(candidate, maximum=maximum + len(_TRUNCATED))
    if len(bounded_source) <= maximum:
        return bounded_source
    if maximum <= len(_TRUNCATED):
        return _TRUNCATED[:maximum]
    return bounded_source[: maximum - len(_TRUNCATED)] + _TRUNCATED

