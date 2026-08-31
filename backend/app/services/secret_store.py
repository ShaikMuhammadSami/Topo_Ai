"""Internal encrypted DB SecretStore. No consumer integration or network I/O.

    with Session(engine) as session, session.begin():
        descriptor = store.put(session, binding, material, operation_id=..., actor=...)
        # Future PH-4C domain row/reference writes share this SAME transaction.

Never commit here. Savepoints make a caught operation failure locally atomic;
the caller still owns the enclosing transaction, including domain persistence.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
import hmac
import json
import os
from typing import Protocol
from uuid import uuid4

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import SecretRecord as R, SecretVersionRecord as V, TenantRecord
from app.models.secret_store import (
    INBOUND_PURPOSES, KEY_ID_PATTERN, MAX_MATERIAL_BYTES, MAX_OVERLAP_SECONDS,
    SECRET_REF_PATTERN, SecretBinding, SecretDescriptor, SecretMaterial,
    SecretPurpose, SecretScope, SecretStoreError,
)
from app.security.secret_keyring import SecretStoreConfiguration

ALGORITHM = "AES-256-GCM"
ENVELOPE_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc)


def _safe_database_errors(method):
    @wraps(method)
    def safe(*args, **kwargs):
        code = None
        try:
            return method(*args, **kwargs)
        except IntegrityError:
            code = "SECRET_OPERATION_CONFLICT"
        except SQLAlchemyError:
            code = "SECRET_STORE_UNAVAILABLE"
        raise SecretStoreError(code)
    return safe


@contextmanager
def _atomic(session):
    connection = session.connection()
    # Python sqlite3 legacy transaction control does not BEGIN for SELECT or
    # SAVEPOINT. Start the caller's physical transaction BEFORE our savepoint,
    # otherwise RELEASE could commit outside the caller's later rollback.
    if connection.dialect.name == "sqlite":
        driver = connection.connection.driver_connection
        if not driver.in_transaction:
            driver.execute("BEGIN")
    with session.begin_nested():
        yield


def _scope_predicate(binding):
    return (
        R.scope_kind == binding.scope.kind, R.scope_id == binding.scope.scope_id,
        R.tenant_id == binding.scope.tenant_id,
        R.owner_type == binding.owner_type, R.owner_id == binding.owner_id,
        R.purpose == binding.purpose.value,
    )


def _metadata(value, limit):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or value != value.strip():
        raise SecretStoreError("SECRET_OPERATION_INVALID")


def _parse_time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError()
    return result


def _binding(record):
    return SecretBinding(SecretScope(record.scope_kind, record.scope_id, record.tenant_id),
                         record.owner_type, record.owner_id, SecretPurpose(record.purpose))


def _usable_versions(record, now):
    try:
        _binding(record)
        if not SECRET_REF_PATTERN.fullmatch(record.secret_ref):
            raise ValueError()
        if record.status not in {"active", "revoked"} or record.row_version < 1 or record.active_version < 1:
            raise ValueError()
        if (record.previous_version is None) != (record.previous_accept_until is None):
            raise ValueError()
        if record.previous_version is not None:
            if not 1 <= record.previous_version < record.active_version:
                raise ValueError()
            if SecretPurpose(record.purpose) not in INBOUND_PURPOSES:
                raise ValueError()
            deadline = _parse_time(record.previous_accept_until)
        if record.status == "revoked":
            return ()
        result = [record.active_version]
        if record.previous_version is not None and now < deadline:
            result.append(record.previous_version)
        return tuple(result)
    except (ValueError, TypeError, SecretStoreError):
        pass
    raise SecretStoreError("SECRET_DECRYPT_FAILED")


def _aad(record, version):
    return json.dumps({
        "scope_kind": record.scope_kind, "scope_id": record.scope_id,
        "tenant_id": record.tenant_id, "secret_ref": record.secret_ref,
        "owner_type": record.owner_type, "owner_id": record.owner_id,
        "purpose": record.purpose, "material_version": version.version,
        "envelope_version": version.envelope_version,
        "algorithm": version.algorithm, "key_id": version.key_id,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class SecretStore(Protocol):
    def put(self, session: Session, binding: SecretBinding, material: SecretMaterial, *, operation_id: str, actor: str) -> SecretDescriptor: ...
    def describe(self, session: Session, binding: SecretBinding, secret_ref: str) -> SecretDescriptor: ...
    def get_for_use(self, session: Session, binding: SecretBinding, secret_ref: str) -> tuple[SecretMaterial, ...]: ...
    def rotate(self, session: Session, binding: SecretBinding, secret_ref: str, material: SecretMaterial, *, operation_id: str, actor: str, expected_row_version: int, overlap_seconds: int = 0) -> SecretDescriptor: ...
    def revoke(self, session: Session, binding: SecretBinding, secret_ref: str, *, actor: str, expected_row_version: int) -> SecretDescriptor: ...
    def rewrap(self, session: Session, binding: SecretBinding, secret_ref: str, *, actor: str, expected_row_version: int) -> SecretDescriptor: ...


class EncryptedDatabaseSecretStore:
    def __init__(self, configuration: SecretStoreConfiguration):
        self.configuration = configuration

    def _authorize(self, session, binding):
        if self.configuration.backend != "encrypted_db":
            raise SecretStoreError("SECRET_STORE_DISABLED")
        if not isinstance(binding, SecretBinding):
            raise SecretStoreError("SECRET_SCOPE_INVALID")
        if binding.scope.kind == "installation":
            if self.configuration.installation_id != binding.scope.scope_id:
                raise SecretStoreError("SECRET_SCOPE_INVALID")
        elif session.scalar(select(TenantRecord.tenant_id).where(
            TenantRecord.tenant_id == binding.scope.tenant_id, TenantRecord.status == "active"
        )) is None:
            raise SecretStoreError("SECRET_NOT_FOUND")

    def _record(self, session, binding, secret_ref=None, *, required=True):
        self._authorize(session, binding)
        query = select(R).where(*_scope_predicate(binding))
        if secret_ref is not None:
            query = query.where(R.secret_ref == secret_ref)
        record = session.scalar(query.execution_options(populate_existing=True))
        if record is None and required:
            raise SecretStoreError("SECRET_NOT_FOUND")
        if record is not None:
            _usable_versions(record, utc_now())
        return record

    def _version(self, session, binding, record, version=None, operation_id=None):
        query = select(V).join(R, R.secret_ref == V.secret_ref).where(
            *_scope_predicate(binding), R.secret_ref == record.secret_ref,
        )
        if version is not None:
            query = query.where(V.version == version)
        if operation_id is not None:
            query = query.where(V.operation_id == operation_id)
        return session.scalar(query.execution_options(populate_existing=True))

    def _decrypt(self, record, version):
        try:
            if (version is None or version.algorithm != ALGORITHM
                or version.envelope_version != ENVELOPE_VERSION or version.version < 1
                or not KEY_ID_PATTERN.fullmatch(version.key_id)
                or len(version.nonce) != 12 or not 17 <= len(version.ciphertext) <= MAX_MATERIAL_BYTES + 16):
                raise ValueError()
            key = self.configuration.keyring.key(version.key_id)
            return SecretMaterial(AESGCM(key).decrypt(version.nonce, version.ciphertext, _aad(record, version)))
        except (InvalidTag, UnsupportedAlgorithm, ValueError, TypeError, SecretStoreError):
            pass
        raise SecretStoreError("SECRET_DECRYPT_FAILED")

    def _encrypt(self, record, version, material):
        if not isinstance(material, SecretMaterial):
            raise SecretStoreError("SECRET_MATERIAL_INVALID")
        version.key_id = self.configuration.keyring.active_key_id
        version.algorithm = ALGORITHM
        version.envelope_version = ENVELOPE_VERSION
        version.nonce = os.urandom(12)
        try:
            version.ciphertext = AESGCM(self.configuration.keyring.key(version.key_id)).encrypt(
                version.nonce, material.reveal(), _aad(record, version))
        except (UnsupportedAlgorithm, ValueError, TypeError):
            pass
        else:
            return
        raise SecretStoreError("SECRET_ENCRYPT_FAILED")

    def _descriptor(self, record):
        versions = _usable_versions(record, utc_now())
        return SecretDescriptor(record.secret_ref, _binding(record), record.status,
            record.active_version, record.previous_version if len(versions) > 1 else None,
            record.previous_accept_until if len(versions) > 1 else None, record.row_version,
            record.created_at, record.updated_at, record.revoked_at)

    def _retry(self, record, version, material, kind, overlap):
        if (not isinstance(material, SecretMaterial) or version.operation_kind != kind
            or version.overlap_seconds != overlap
            or not hmac.compare_digest(self._decrypt(record, version).reveal(), material.reveal())):
            raise SecretStoreError("SECRET_OPERATION_CONFLICT")
        return self._descriptor(record)

    def _cas(self, session, binding, record, expected, actor, **values):
        _metadata(actor, 500)
        if type(expected) is not int or expected < 1 or record.row_version != expected:
            raise SecretStoreError("SECRET_CONCURRENT_MODIFICATION")
        result = session.execute(update(R).where(
            *_scope_predicate(binding), R.secret_ref == record.secret_ref,
            R.row_version == expected, R.active_version == record.active_version, R.status == "active",
        ).values(**values, row_version=expected + 1, updated_at=utc_now().isoformat(),
                 updated_by_subject=actor).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise SecretStoreError("SECRET_CONCURRENT_MODIFICATION")

    @_safe_database_errors
    def put(self, session, binding, material, *, operation_id, actor):
        _metadata(operation_id, 128)
        _metadata(actor, 500)
        with _atomic(session):
            record = self._record(session, binding, required=False)
            if record is not None:
                if record.status == "revoked":
                    raise SecretStoreError("SECRET_REVOKED")
                version = self._version(session, binding, record, operation_id=operation_id)
                if version is None:
                    raise SecretStoreError("SECRET_OPERATION_CONFLICT")
                return self._retry(record, version, material, "put", 0)
            now = utc_now().isoformat()
            record = R(secret_ref=f"secret:{uuid4()}", scope_kind=binding.scope.kind,
                scope_id=binding.scope.scope_id, tenant_id=binding.scope.tenant_id,
                owner_type=binding.owner_type, owner_id=binding.owner_id, purpose=binding.purpose.value,
                status="active", active_version=1, previous_version=None, previous_accept_until=None,
                row_version=1, created_at=now, updated_at=now, created_by_subject=actor,
                updated_by_subject=actor, revoked_at=None)
            version = V(secret_ref=record.secret_ref, version=1, operation_id=operation_id,
                operation_kind="put", overlap_seconds=0, envelope_revision=1, created_at=now,
                created_by_subject=actor)
            self._encrypt(record, version, material)
            session.add(record)
            session.flush()
            session.add(version)
            session.flush()
            return self._descriptor(record)

    @_safe_database_errors
    def describe(self, session, binding, secret_ref):
        with session.no_autoflush:
            return self._descriptor(self._record(session, binding, secret_ref))

    @_safe_database_errors
    def get_for_use(self, session, binding, secret_ref):
        with session.no_autoflush:
            record = self._record(session, binding, secret_ref)
            if record.status == "revoked":
                raise SecretStoreError("SECRET_REVOKED")
            return tuple(self._decrypt(record, self._version(session, binding, record, version=v))
                         for v in _usable_versions(record, utc_now()))

    @_safe_database_errors
    def rotate(self, session, binding, secret_ref, material, *, operation_id, actor,
               expected_row_version, overlap_seconds=0):
        _metadata(operation_id, 128)
        if (type(overlap_seconds) is not int or not 0 <= overlap_seconds <= MAX_OVERLAP_SECONDS
            or (binding.purpose not in INBOUND_PURPOSES and overlap_seconds != 0)):
            raise SecretStoreError("SECRET_OVERLAP_INVALID")
        with _atomic(session):
            record = self._record(session, binding, secret_ref)
            if record.status == "revoked":
                raise SecretStoreError("SECRET_REVOKED")
            retry = self._version(session, binding, record, operation_id=operation_id)
            if retry is not None:
                return self._retry(record, retry, material, "rotate", overlap_seconds)
            now = utc_now()
            version = V(secret_ref=record.secret_ref, version=record.active_version + 1,
                operation_id=operation_id, operation_kind="rotate", overlap_seconds=overlap_seconds,
                envelope_revision=1, created_at=now.isoformat(), created_by_subject=actor)
            self._encrypt(record, version, material)
            self._cas(session, binding, record, expected_row_version, actor,
                active_version=version.version, previous_version=record.active_version if overlap_seconds else None,
                previous_accept_until=(now + timedelta(seconds=overlap_seconds)).isoformat() if overlap_seconds else None)
            session.add(version)
            session.flush()
            return self._descriptor(self._record(session, binding, secret_ref))

    @_safe_database_errors
    def revoke(self, session, binding, secret_ref, *, actor, expected_row_version):
        with _atomic(session):
            record = self._record(session, binding, secret_ref)
            if record.status == "revoked":
                return self._descriptor(record)
            self._cas(session, binding, record, expected_row_version, actor, status="revoked",
                      revoked_at=utc_now().isoformat(), previous_version=None, previous_accept_until=None)
            return self._descriptor(self._record(session, binding, secret_ref))

    @_safe_database_errors
    def rewrap(self, session, binding, secret_ref, *, actor, expected_row_version):
        with _atomic(session):
            record = self._record(session, binding, secret_ref)
            if record.status == "revoked":
                raise SecretStoreError("SECRET_REVOKED")
            replacements = []
            for number in _usable_versions(record, utc_now()):
                version = self._version(session, binding, record, version=number)
                material = self._decrypt(record, version)
                if version.key_id == self.configuration.keyring.active_key_id:
                    continue
                replacement = V(version=number)
                self._encrypt(record, replacement, material)
                replacements.append((version, replacement))
            if not replacements:
                return self._descriptor(record)
            self._cas(session, binding, record, expected_row_version, actor)
            for old, replacement in replacements:
                result = session.execute(update(V).where(
                    V.secret_ref == record.secret_ref, V.version == old.version,
                    V.envelope_revision == old.envelope_revision, V.key_id == old.key_id,
                ).values(key_id=replacement.key_id, nonce=replacement.nonce, ciphertext=replacement.ciphertext,
                         envelope_revision=old.envelope_revision + 1, rewrapped_at=utc_now().isoformat(),
                         rewrapped_by_subject=actor).execution_options(synchronize_session=False))
                if result.rowcount != 1:
                    raise SecretStoreError("SECRET_CONCURRENT_MODIFICATION")
            return self._descriptor(self._record(session, binding, secret_ref))

    @_safe_database_errors
    def validate_readiness(self, session):
        """Bounded keyset pages of metadata; no ciphertext, plaintext or decryption."""
        if self.configuration.backend == "disabled":
            if session.scalar(select(R.secret_ref).limit(1)) is not None or session.scalar(select(V.secret_ref).limit(1)) is not None:
                raise SecretStoreError("SECRET_STORE_DISABLED")
            return
        cursor = None
        while True:
            query = select(R).order_by(R.secret_ref).limit(256)
            if cursor is not None:
                query = query.where(R.secret_ref > cursor)
            records = session.scalars(query).all()
            if not records:
                return
            for record in records:
                if record.scope_kind == "installation" and record.scope_id != self.configuration.installation_id:
                    raise SecretStoreError("SECRET_SCOPE_INVALID")
                for version in _usable_versions(record, utc_now()):
                    metadata = session.execute(select(V.key_id, V.algorithm, V.envelope_version).where(
                        V.secret_ref == record.secret_ref, V.version == version)).one_or_none()
                    if metadata is None or metadata.algorithm != ALGORITHM or metadata.envelope_version != ENVELOPE_VERSION:
                        raise SecretStoreError("SECRET_DECRYPT_FAILED")
                    if not self.configuration.keyring.contains(metadata.key_id):
                        raise SecretStoreError("SECRET_REQUIRED_KEY_MISSING")
            cursor = records[-1].secret_ref
