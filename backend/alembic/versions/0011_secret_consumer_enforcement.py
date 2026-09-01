"""Enforce reference-only provider and webhook reversible-secret custody.

Revision ID: 0011_secret_enforce
Revises: 0010_secret_refs

This migration performs metadata-only preflight. It never reads environment
credentials, decrypts SecretStore material, or guesses tenant/owner authority.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlparse

from alembic import op
import sqlalchemy as sa


revision = "0011_secret_enforce"
down_revision = "0010_secret_refs"
branch_labels = None
depends_on = None

SECRET_REF = re.compile(
    r"secret:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
COMMON_CONFIG = {"environment", "cluster_name", "namespace", "entity_refs"}
CONFIG_FIELDS = {
    "github": COMMON_CONFIG | {"source_file_capture"},
    "gitlab": COMMON_CONFIG | {"auth_mode", "signature_max_age"},
    "jenkins": COMMON_CONFIG,
    "azure_devops": COMMON_CONFIG | {"username"},
    "terraform_cloud": COMMON_CONFIG | {"provider"},
}
FILTER_FIELDS = {"event_types", "repositories", "environments"}
ENTITY_FIELDS = {
    "entity_id", "external_id", "provider_resource_id", "kind", "name",
    "namespace", "cluster_name",
}
CAPTURE_LIMITS = {
    "maximum_commits": 20,
    "maximum_files": 100,
    "maximum_bytes_per_file": 65536,
    "maximum_total_bytes": 524288,
    "maximum_scalar_bytes": 256,
    "maximum_scalar_characters": 128,
}
CREDENTIAL_QUERY_KEYS = {
    "accesskey", "accesstoken", "apikey", "auth", "authorization",
    "credential", "key", "password", "secret", "signature", "sig", "token",
}


def _document(raw, default):
    try:
        value = json.loads(raw if raw is not None else default)
    except (TypeError, json.JSONDecodeError):
        return None
    return value


def _optional_text(value, maximum=255):
    return value is None or (
        isinstance(value, str) and len(value) <= maximum
    )


def _config_valid(source_type, config, filters):
    allowed = CONFIG_FIELDS.get(source_type)
    if allowed is None or not isinstance(config, dict) or set(config) - allowed:
        return False
    for name in ("environment", "cluster_name", "namespace", "provider"):
        if name in config and not _optional_text(config[name]):
            return False
    if "username" in config and not (
        isinstance(config["username"], str) and 1 <= len(config["username"]) <= 255
    ):
        return False
    if source_type == "gitlab":
        if config.get("auth_mode", "signing") not in {"signing", "secret_token"}:
            return False
        age = config.get("signature_max_age", 300)
        if type(age) is not int or not 1 <= age <= 3600:
            return False
    refs = config.get("entity_refs", [])
    if not isinstance(refs, list) or len(refs) > 100:
        return False
    for item in refs:
        if not isinstance(item, dict) or set(item) - ENTITY_FIELDS:
            return False
        if any(not _optional_text(value, 1000) for value in item.values()):
            return False
    capture = config.get("source_file_capture", {})
    if not isinstance(capture, dict) or set(capture) - set(CAPTURE_LIMITS):
        return False
    for name, maximum in CAPTURE_LIMITS.items():
        value = capture.get(name, maximum)
        if type(value) is not int or not 1 <= value <= maximum:
            return False
    if not isinstance(filters, dict) or set(filters) - FILTER_FIELDS:
        return False
    for value in filters.values():
        if (
            not isinstance(value, list)
            or len(value) > 100
            or any(not isinstance(item, str) or len(item) > 1000 for item in value)
        ):
            return False
    return True


def _purpose(source_type, config):
    if source_type == "github":
        return "change_source.github_hmac"
    if source_type == "gitlab":
        return (
            "change_source.gitlab_shared_token"
            if config.get("auth_mode", "signing") == "secret_token"
            else "change_source.gitlab_signing"
        )
    return {
        "terraform_cloud": "change_source.terraform_hmac",
        "jenkins": "change_source.jenkins_hmac",
        "azure_devops": "change_source.azure_basic_password",
    }.get(source_type)


def _binding_exists(connection, *, secret_ref, tenant_id, owner_type, owner_id, purpose):
    return connection.execute(
        sa.text(
            "SELECT 1 FROM secret_records WHERE secret_ref = :secret_ref "
            "AND scope_kind = 'tenant' AND scope_id = :tenant_id "
            "AND tenant_id = :tenant_id AND owner_type = :owner_type "
            "AND owner_id = :owner_id AND purpose = :purpose "
            "AND status = 'active' LIMIT 1"
        ),
        {
            "secret_ref": secret_ref,
            "tenant_id": tenant_id,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "purpose": purpose,
        },
    ).first() is not None


def _url_valid(value):
    try:
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            return False
        return not any(
            re.sub(r"[^a-z0-9]", "", name.lower()) in CREDENTIAL_QUERY_KEYS
            for name, _ in parse_qsl(parsed.query, keep_blank_values=True)
        )
    except (TypeError, ValueError):
        return False


def _preflight(connection):
    sources = connection.execute(sa.text(
        "SELECT tenant_id, source_id, source_type, enabled, secret_ref, "
        "config_json, filters_json FROM change_sources"
    )).mappings()
    for row in sources:
        config = _document(row["config_json"], "{}")
        filters = _document(row["filters_json"], "{}")
        if not _config_valid(row["source_type"], config, filters):
            raise RuntimeError("LEGACY_SOURCE_CONFIG_REVIEW_REQUIRED")
        secret_ref = row["secret_ref"]
        if secret_ref is None:
            if row["enabled"]:
                raise RuntimeError("LEGACY_SECRET_CONVERSION_REQUIRED")
            continue
        if not isinstance(secret_ref, str) or not SECRET_REF.fullmatch(secret_ref):
            if isinstance(secret_ref, str) and not secret_ref.startswith("secret:"):
                raise RuntimeError("LEGACY_SECRET_CONVERSION_REQUIRED")
            raise RuntimeError("LEGACY_SOURCE_SECRET_REFERENCE_INVALID")
        purpose = _purpose(row["source_type"], config)
        if purpose is None or not _binding_exists(
            connection,
            secret_ref=secret_ref,
            tenant_id=row["tenant_id"],
            owner_type="change_source",
            owner_id=row["source_id"],
            purpose=purpose,
        ):
            raise RuntimeError("SECRET_CONSUMER_BINDING_INVALID")

    endpoints = connection.execute(sa.text(
        "SELECT tenant_id, webhook_id, url, signing_secret, headers_json, "
        "signing_secret_ref, protected_headers_secret_ref, "
        "protected_header_names_json FROM webhook_endpoints"
    )).mappings()
    for row in endpoints:
        headers = _document(row["headers_json"], "{}")
        names = _document(row["protected_header_names_json"], "[]")
        if row["signing_secret"] not in {None, ""} or headers != {}:
            raise RuntimeError("LEGACY_WEBHOOK_SECRET_CONVERSION_REQUIRED")
        if not _url_valid(row["url"]):
            raise RuntimeError("LEGACY_WEBHOOK_SECRET_CONVERSION_REQUIRED")
        if (
            not isinstance(names, list)
            or any(not isinstance(name, str) or len(name) > 128 for name in names)
            or len({name.lower() for name in names}) != len(names)
            or (row["protected_headers_secret_ref"] is None) != (names == [])
        ):
            raise RuntimeError("SECRET_CONSUMER_BINDING_INVALID")
        for ref_name, purpose in (
            ("signing_secret_ref", "webhook_endpoint.signing"),
            ("protected_headers_secret_ref", "webhook_endpoint.protected_headers"),
        ):
            secret_ref = row[ref_name]
            if secret_ref is not None and (
                not isinstance(secret_ref, str)
                or not SECRET_REF.fullmatch(secret_ref)
                or not _binding_exists(
                    connection,
                    secret_ref=secret_ref,
                    tenant_id=row["tenant_id"],
                    owner_type="webhook_endpoint",
                    owner_id=row["webhook_id"],
                    purpose=purpose,
                )
            ):
                raise RuntimeError("SECRET_CONSUMER_BINDING_INVALID")
        if bool(row["protected_headers_secret_ref"]) != bool(names):
            raise RuntimeError("SECRET_CONSUMER_BINDING_INVALID")


def upgrade():
    connection = op.get_bind()
    _preflight(connection)

    with op.batch_alter_table("change_sources") as batch:
        batch.alter_column(
            "secret_ref", existing_type=sa.String(255), type_=sa.String(64),
            existing_nullable=True,
        )
        batch.create_check_constraint(
            "ck_change_sources_secret_ref",
            "secret_ref IS NULL OR "
            "(length(secret_ref) = 43 AND substr(secret_ref, 1, 7) = 'secret:')",
        )
        batch.create_check_constraint(
            "ck_change_sources_enabled_secret",
            "NOT enabled OR secret_ref IS NOT NULL",
        )

    with op.batch_alter_table("webhook_endpoints") as batch:
        batch.alter_column(
            "protected_header_names_json",
            existing_type=sa.Text(),
            existing_nullable=False,
            server_default=None,
        )
        batch.create_check_constraint(
            "ck_webhook_signing_secret_ref",
            "signing_secret_ref IS NULL OR "
            "(length(signing_secret_ref) = 43 AND substr(signing_secret_ref, 1, 7) = 'secret:')",
        )
        batch.create_check_constraint(
            "ck_webhook_headers_secret_ref",
            "protected_headers_secret_ref IS NULL OR "
            "(length(protected_headers_secret_ref) = 43 "
            "AND substr(protected_headers_secret_ref, 1, 7) = 'secret:')",
        )
        batch.drop_column("headers_json")
        batch.drop_column("signing_secret")


def downgrade():
    with op.batch_alter_table("webhook_endpoints") as batch:
        batch.add_column(sa.Column("signing_secret", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("headers_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.drop_constraint("ck_webhook_headers_secret_ref", type_="check")
        batch.drop_constraint("ck_webhook_signing_secret_ref", type_="check")

    with op.batch_alter_table("change_sources") as batch:
        batch.drop_constraint("ck_change_sources_enabled_secret", type_="check")
        batch.drop_constraint("ck_change_sources_secret_ref", type_="check")
        batch.alter_column(
            "secret_ref", existing_type=sa.String(64), type_=sa.String(255),
            existing_nullable=True,
        )
