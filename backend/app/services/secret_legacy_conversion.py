"""Exact-0010 operator conversion for legacy provider/webhook credentials."""

from __future__ import annotations

import json
import hashlib
import os
import re
import stat
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.secret_store import SECRET_REF_PATTERN, SecretMaterial, SecretPurpose
from app.security.secret_keyring import load_secret_store_configuration
from app.services.secret_consumer_policy import (
    ProviderPolicyError,
    serialize_protected_headers,
    source_binding,
    validate_protected_headers,
    validate_provider_configuration,
    validate_webhook_url,
    webhook_binding,
)
from app.services.secret_store import EncryptedDatabaseSecretStore, SecretStore


CONVERSION_REVISION = "0010_secret_refs"
MAX_MANIFEST_BYTES = 65536
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,254}\Z")

metadata = sa.MetaData()
sources = sa.Table(
    "change_sources", metadata,
    sa.Column("tenant_id", sa.String), sa.Column("source_id", sa.String),
    sa.Column("source_type", sa.String), sa.Column("enabled", sa.Boolean),
    sa.Column("secret_ref", sa.String), sa.Column("config_json", sa.Text),
    sa.Column("filters_json", sa.Text), sa.Column("status", sa.String),
    sa.Column("updated_at", sa.String),
)
endpoints = sa.Table(
    "webhook_endpoints", metadata,
    sa.Column("tenant_id", sa.String), sa.Column("webhook_id", sa.String),
    sa.Column("url", sa.String), sa.Column("active", sa.Boolean),
    sa.Column("signing_secret", sa.Text), sa.Column("headers_json", sa.Text),
    sa.Column("signing_secret_ref", sa.String),
    sa.Column("protected_headers_secret_ref", sa.String),
    sa.Column("protected_header_names_json", sa.Text),
    sa.Column("updated_at", sa.String),
)
tenants = sa.Table(
    "tenants", metadata, sa.Column("tenant_id", sa.String), sa.Column("status", sa.String)
)


class LegacyConversionError(RuntimeError):
    pass


def _conversion_operation(owner_id: str, purpose: str) -> str:
    return "ph4c:v1:" + hashlib.sha256(
        f"{owner_id}|{purpose}".encode("utf-8")
    ).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def load_conversion_manifest(path: str) -> dict:
    try:
        candidate = Path(path)
        if not path or not candidate.is_absolute():
            raise ValueError()
        for part in (candidate, *candidate.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError()
        before = candidate.lstat()
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_MANIFEST_BYTES:
            raise ValueError()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(candidate, flags), "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ValueError()
            data = handle.read(MAX_MANIFEST_BYTES + 1)
        document = json.loads(data, object_pairs_hook=_unique_object)
        _validate_manifest(document)
        return document
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise LegacyConversionError("LEGACY_CONVERSION_MANIFEST_INVALID") from None


def _validate_manifest(document: dict) -> None:
    if not isinstance(document, dict) or set(document) != {"version", "sources", "webhooks"}:
        raise ValueError()
    if document["version"] != 1 or not isinstance(document["sources"], list) or not isinstance(document["webhooks"], list):
        raise ValueError()
    seen_sources: set[tuple[str, str]] = set()
    for entry in document["sources"]:
        required = {
            "source_id", "tenant_id", "expected_provider",
            "expected_legacy_env_name", "action",
        }
        if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - (required | {"expected_auth_mode"}):
            raise ValueError()
        if entry["action"] not in {"import", "discard_and_disable"}:
            raise ValueError()
        if not all(isinstance(entry[name], str) and entry[name] for name in required):
            raise ValueError()
        if not ENV_NAME.fullmatch(entry["expected_legacy_env_name"]):
            raise ValueError()
        if "expected_auth_mode" in entry and entry["expected_auth_mode"] not in {"signing", "secret_token"}:
            raise ValueError()
        key = (entry["tenant_id"], entry["source_id"])
        if key in seen_sources:
            raise ValueError()
        seen_sources.add(key)
    seen_webhooks: set[tuple[str, str]] = set()
    for entry in document["webhooks"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"webhook_id", "tenant_id", "action"}
            or entry["action"] != "discard_and_disable"
            or not isinstance(entry["webhook_id"], str)
            or not isinstance(entry["tenant_id"], str)
        ):
            raise ValueError()
        key = (entry["tenant_id"], entry["webhook_id"])
        if key in seen_webhooks:
            raise ValueError()
        seen_webhooks.add(key)


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        values = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
    if values != [CONVERSION_REVISION]:
        raise LegacyConversionError("LEGACY_CONVERSION_REVISION_REQUIRED")
    return values[0]


def _document(raw: str, code: str) -> dict:
    try:
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (TypeError, ValueError, json.JSONDecodeError):
        raise LegacyConversionError(code) from None


def _names_document(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        if (
            not isinstance(value, list)
            or len(value) > 32
            or any(not isinstance(name, str) or not 1 <= len(name) <= 128 for name in value)
            or len({name.lower() for name in value}) != len(value)
        ):
            raise ValueError()
        return value
    except (TypeError, ValueError, json.JSONDecodeError):
        raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID") from None


def _binding_is_active(session: Session, binding, secret_ref: str) -> bool:
    return session.execute(
        sa.text(
            "SELECT 1 FROM secret_records WHERE secret_ref = :secret_ref "
            "AND scope_kind = :scope_kind AND scope_id = :scope_id "
            "AND ((tenant_id = :tenant_id) OR (tenant_id IS NULL AND :tenant_id IS NULL)) "
            "AND owner_type = :owner_type AND owner_id = :owner_id "
            "AND purpose = :purpose AND status = 'active' LIMIT 1"
        ),
        {
            "secret_ref": secret_ref,
            "scope_kind": binding.scope.kind,
            "scope_id": binding.scope.scope_id,
            "tenant_id": binding.scope.tenant_id,
            "owner_type": binding.owner_type,
            "owner_id": binding.owner_id,
            "purpose": binding.purpose.value,
        },
    ).first() is not None


def _validate_existing_binding(
    session: Session,
    *,
    binding,
    secret_ref: str | None,
    store: SecretStore | None,
) -> None:
    if secret_ref is None:
        return
    if (
        not isinstance(secret_ref, str)
        or not SECRET_REF_PATTERN.fullmatch(secret_ref)
        or not _binding_is_active(session, binding, secret_ref)
    ):
        raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID")
    if store is not None:
        try:
            store.describe(session, binding, secret_ref)
        except Exception:
            raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID") from None


def _tenant_active(session: Session, tenant_id: str) -> bool:
    return session.execute(
        sa.select(tenants.c.status).where(tenants.c.tenant_id == tenant_id)
    ).scalar_one_or_none() == "active"


def _source_status(
    session: Session, entry: dict, *, apply: bool, store: SecretStore | None
) -> dict:
    row = session.execute(
        sa.select(sources).where(
            sources.c.tenant_id == entry["tenant_id"],
            sources.c.source_id == entry["source_id"],
        ).with_for_update()
    ).mappings().one_or_none()
    if row is None:
        raise LegacyConversionError("LEGACY_SOURCE_MANIFEST_MISMATCH")
    config_raw = _document(row["config_json"], "LEGACY_SOURCE_CONFIG_REVIEW_REQUIRED")
    filters_raw = _document(row["filters_json"], "LEGACY_SOURCE_CONFIG_REVIEW_REQUIRED")
    try:
        config, _ = validate_provider_configuration(row["source_type"], config_raw, filters_raw)
        binding = source_binding(
            tenant_id=row["tenant_id"], source_id=row["source_id"],
            source_type=row["source_type"], config=config,
        )
    except ProviderPolicyError:
        raise LegacyConversionError("LEGACY_SOURCE_CONFIG_REVIEW_REQUIRED") from None
    auth_mode = config.get("auth_mode", "signing") if row["source_type"] == "gitlab" else None
    if (
        row["tenant_id"] != entry["tenant_id"]
        or row["source_type"] != entry["expected_provider"]
        or (entry.get("expected_auth_mode") is not None and auth_mode != entry["expected_auth_mode"])
    ):
        raise LegacyConversionError("LEGACY_SOURCE_MANIFEST_MISMATCH")
    legacy_name = entry["expected_legacy_env_name"]
    current_ref = row["secret_ref"]
    if isinstance(current_ref, str) and SECRET_REF_PATTERN.fullmatch(current_ref):
        _validate_existing_binding(
            session, binding=binding, secret_ref=current_ref, store=store
        )
        return {"owner_id": row["source_id"], "provider": row["source_type"], "purpose": binding.purpose.value, "status": "already_converted"}
    if entry["action"] == "discard_and_disable" and current_ref is None and not row["enabled"]:
        return {"owner_id": row["source_id"], "provider": row["source_type"], "purpose": binding.purpose.value, "status": "already_discarded"}
    if current_ref != legacy_name:
        raise LegacyConversionError("LEGACY_SOURCE_MANIFEST_MISMATCH")
    active_tenant = _tenant_active(session, row["tenant_id"])
    if entry["action"] == "import" and not active_tenant:
        raise LegacyConversionError("LEGACY_DISABLED_OWNER_REQUIRES_DISCARD")
    result = {"owner_id": row["source_id"], "provider": row["source_type"], "purpose": binding.purpose.value, "status": "would_" + entry["action"]}
    if not apply:
        return result
    if entry["action"] == "discard_and_disable":
        session.execute(
            sa.update(sources).where(
                sources.c.tenant_id == row["tenant_id"], sources.c.source_id == row["source_id"]
            ).values(secret_ref=None, enabled=False, status="disabled")
        )
        result["status"] = "discarded"
        return result
    # The exact manifest/row/tenant/provider/auth-mode match is complete before this lookup.
    raw = os.environ.get(legacy_name)
    if raw is None:
        raise LegacyConversionError("LEGACY_SOURCE_ENVIRONMENT_MISSING")
    assert store is not None
    descriptor = store.put(
        session, binding, SecretMaterial(raw.encode("utf-8")),
        operation_id=_conversion_operation(row["source_id"], binding.purpose.value),
        actor="operator:ph4c-legacy-converter",
    )
    session.execute(
        sa.update(sources).where(
            sources.c.tenant_id == row["tenant_id"], sources.c.source_id == row["source_id"]
        ).values(secret_ref=descriptor.secret_ref)
    )
    result["status"] = "converted"
    return result


def _webhook_status(
    session: Session, row: dict, discard: set[tuple[str, str]], *, apply: bool,
    store: SecretStore | None,
) -> dict:
    key = (row["tenant_id"], row["webhook_id"])
    try:
        validate_webhook_url(row["url"])
    except ProviderPolicyError:
        raise LegacyConversionError("LEGACY_WEBHOOK_URL_REVIEW_REQUIRED") from None
    legacy_headers = _document(row["headers_json"], "LEGACY_WEBHOOK_HEADERS_INVALID")
    names = _names_document(row["protected_header_names_json"])
    try:
        headers = validate_protected_headers(legacy_headers)
    except ProviderPolicyError:
        raise LegacyConversionError("LEGACY_WEBHOOK_HEADERS_INVALID") from None
    has_legacy = bool(row["signing_secret"]) or bool(headers)
    signing_binding = webhook_binding(
        tenant_id=row["tenant_id"], webhook_id=row["webhook_id"],
        purpose=SecretPurpose.WEBHOOK_SIGNING,
    )
    headers_binding = webhook_binding(
        tenant_id=row["tenant_id"], webhook_id=row["webhook_id"],
        purpose=SecretPurpose.WEBHOOK_HEADERS,
    )
    _validate_existing_binding(
        session, binding=signing_binding,
        secret_ref=row["signing_secret_ref"], store=store,
    )
    _validate_existing_binding(
        session, binding=headers_binding,
        secret_ref=row["protected_headers_secret_ref"], store=store,
    )
    expected_names = sorted(headers, key=str.lower)
    if row["protected_headers_secret_ref"]:
        if headers and names != expected_names:
            raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID")
        if not headers and not names:
            raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID")
    elif names:
        raise LegacyConversionError("SECRET_CONSUMER_BINDING_INVALID")
    active_tenant = _tenant_active(session, row["tenant_id"])
    if not active_tenant and has_legacy and key not in discard:
        raise LegacyConversionError("LEGACY_DISABLED_OWNER_REQUIRES_DISCARD")
    result = {"owner_id": row["webhook_id"], "provider": "outbound_webhook", "purpose": "webhook_endpoint", "status": "already_converted" if not has_legacy else "would_convert"}
    if not apply:
        if not active_tenant and key in discard:
            result["status"] = "would_discard_and_disable"
        return result
    if not active_tenant:
        session.execute(
            sa.update(endpoints).where(
                endpoints.c.tenant_id == row["tenant_id"], endpoints.c.webhook_id == row["webhook_id"]
            ).values(
                active=False, signing_secret=None, headers_json="{}",
                signing_secret_ref=None, protected_headers_secret_ref=None,
                protected_header_names_json="[]",
            )
        )
        result["status"] = "discarded"
        return result
    assert store is not None
    values = {"signing_secret": None, "headers_json": "{}"}
    if row["signing_secret"]:
        binding = signing_binding
        if row["signing_secret_ref"]:
            signing_ref = row["signing_secret_ref"]
        else:
            signing_ref = store.put(
                session, binding, SecretMaterial(row["signing_secret"].encode("utf-8")),
                operation_id=_conversion_operation(row["webhook_id"], "signing"),
                actor="operator:ph4c-legacy-converter",
            ).secret_ref
        values["signing_secret_ref"] = signing_ref
    if headers:
        binding = headers_binding
        if row["protected_headers_secret_ref"]:
            headers_ref = row["protected_headers_secret_ref"]
        else:
            headers_ref = store.put(
                session, binding, SecretMaterial(serialize_protected_headers(headers)),
                operation_id=_conversion_operation(row["webhook_id"], "headers"),
                actor="operator:ph4c-legacy-converter",
            ).secret_ref
        values.update(
            protected_headers_secret_ref=headers_ref,
            protected_header_names_json=json.dumps(sorted(headers, key=str.lower), separators=(",", ":")),
        )
    session.execute(
        sa.update(endpoints).where(
            endpoints.c.tenant_id == row["tenant_id"], endpoints.c.webhook_id == row["webhook_id"]
        ).values(**values)
    )
    result["status"] = "converted" if has_legacy else "already_converted"
    return result


def convert_legacy_secrets(
    engine: Engine, manifest: dict, *, apply: bool = False, store: SecretStore | None = None
) -> dict:
    try:
        _validate_manifest(manifest)
    except (TypeError, ValueError):
        raise LegacyConversionError("LEGACY_CONVERSION_MANIFEST_INVALID") from None
    _revision(engine)
    if apply and store is None:
        store = EncryptedDatabaseSecretStore(load_secret_store_configuration())
    results = []
    for entry in manifest["sources"]:
        with Session(engine) as session, session.begin():
            results.append(_source_status(session, entry, apply=apply, store=store))
    discard = {(entry["tenant_id"], entry["webhook_id"]) for entry in manifest["webhooks"]}
    with Session(engine) as session:
        rows = session.execute(sa.select(endpoints)).mappings().all()
    known = {(row["tenant_id"], row["webhook_id"]) for row in rows}
    if discard - known:
        raise LegacyConversionError("LEGACY_WEBHOOK_MANIFEST_MISMATCH")
    for row in rows:
        with Session(engine) as session, session.begin():
            fresh = session.execute(
                sa.select(endpoints).where(
                    endpoints.c.tenant_id == row["tenant_id"], endpoints.c.webhook_id == row["webhook_id"]
                ).with_for_update()
            ).mappings().one()
            results.append(_webhook_status(session, fresh, discard, apply=apply, store=store))
    return {
        "mode": "apply" if apply else "dry_run",
        "converted": sum(item["status"] == "converted" for item in results),
        "discarded": sum(item["status"] == "discarded" for item in results),
        "blocked": 0,
        "objects": results,
    }
