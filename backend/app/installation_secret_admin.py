"""Local operator administration for installation-scoped outbound secrets.

This module deliberately has no HTTP surface. Secret material enters through a
hidden prompt, stdin, or the three fixed legacy import variables only.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.models.secret_store import SecretMaterial, SecretStoreError
from app.models.security_audit import SecurityAuditAction, SecurityAuditResourceType
from app.security.authorization_policy import Permission
from app.security.secret_keyring import load_secret_store_configuration
from app.services.installation_secrets import (
    INSTALLATION_INTEGRATIONS,
    installation_binding,
)
from app.services.secret_store import EncryptedDatabaseSecretStore
from app.services.security_audit import append_local_operator_security_event

_KNOWN_IMPORTS = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "github": "TOPO_GITHUB_TOKEN",
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="python -m app.installation_secret_admin",
        description="Manage encrypted installation integration credentials.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("integration", nargs="?", choices=tuple(_KNOWN_IMPORTS))
    for command in ("set", "reprovision", "rotate", "import-known-env"):
        item = subparsers.add_parser(command)
        item.add_argument("integration", choices=tuple(_KNOWN_IMPORTS))
        item.add_argument("--operation-id")
        if command != "import-known-env":
            source = item.add_mutually_exclusive_group()
            source.add_argument("--secret-stdin", action="store_true")
            source.add_argument("--prompt", action="store_true")
    revoke = subparsers.add_parser("revoke")
    revoke.add_argument("integration", choices=tuple(_KNOWN_IMPORTS))
    return parser


def _material(args: argparse.Namespace) -> SecretMaterial:
    if args.command == "import-known-env":
        value = os.environ.get(_KNOWN_IMPORTS[args.integration], "")
    elif args.secret_stdin:
        value = sys.stdin.read()
    else:
        value = getpass.getpass(f"{args.integration} credential: ")
    raw = value.strip().encode("utf-8")
    if not raw:
        raise SecretStoreError("SECRET_MATERIAL_INVALID")
    return SecretMaterial(raw)


def _safe_status(store: EncryptedDatabaseSecretStore, session: Session, name: str):
    try:
        descriptor = store.describe_for_binding(session, installation_binding(name))
        result = {
            "integration": name,
            "configured": descriptor.status == "active",
            "status": descriptor.status,
            "updated_at": descriptor.updated_at,
        }
    except SecretStoreError as exc:
        if str(exc) == "SECRET_NOT_FOUND":
            result = {
                "integration": name,
                "configured": False,
                "status": "unconfigured",
                "updated_at": None,
            }
        else:
            raise
    append_local_operator_security_event(
        session,
        action=SecurityAuditAction.INSTALLATION_SECRET_INSPECTED,
        permissions=[Permission.INSTALLATION_STATUS_READ],
        resource_type=SecurityAuditResourceType.SECRET_RECORD,
        resource_id=name,
    )
    session.commit()
    return result


def _mutate(
    store: EncryptedDatabaseSecretStore,
    session: Session,
    args: argparse.Namespace,
) -> dict[str, object]:
    binding = installation_binding(args.integration)
    actor = f"installation-secret-admin:{getpass.getuser()[:200]}"
    operation_id: str | None = None
    if args.command == "revoke":
        descriptor = store.describe_for_binding(session, binding)
        result = store.revoke(
            session,
            binding,
            descriptor.secret_ref,
            actor=actor,
            expected_row_version=descriptor.row_version,
        )
    else:
        operation_id = args.operation_id or f"admin:{args.command}:{uuid4()}"
        material = _material(args)
        if args.command in {"set", "import-known-env"}:
            result = store.put(
                session,
                binding,
                material,
                operation_id=operation_id,
                actor=actor,
            )
        else:
            descriptor = store.describe_for_binding(session, binding)
            if args.command == "rotate":
                result = store.rotate(
                    session,
                    binding,
                    descriptor.secret_ref,
                    material,
                    operation_id=operation_id,
                    actor=actor,
                    expected_row_version=descriptor.row_version,
                    overlap_seconds=0,
                )
            else:
                result = store.reprovision(
                    session,
                    binding,
                    descriptor.secret_ref,
                    material,
                    operation_id=operation_id,
                    actor=actor,
                    expected_row_version=descriptor.row_version,
                )
    audit_actions = {
        "set": SecurityAuditAction.INSTALLATION_SECRET_SET,
        "reprovision": SecurityAuditAction.INSTALLATION_SECRET_REPROVISIONED,
        "rotate": SecurityAuditAction.INSTALLATION_SECRET_ROTATED,
        "import-known-env": SecurityAuditAction.INSTALLATION_SECRET_IMPORTED,
        "revoke": SecurityAuditAction.INSTALLATION_SECRET_REVOKED,
    }
    append_local_operator_security_event(
        session,
        action=audit_actions[args.command],
        permissions=[Permission.INSTALLATION_SECRET_MANAGE],
        resource_type=SecurityAuditResourceType.SECRET_RECORD,
        resource_id=args.integration,
    )
    session.commit()
    output: dict[str, object] = {
        "integration": args.integration,
        "configured": result.status == "active",
        "status": result.status,
        "updated_at": result.updated_at,
        "operation": args.command,
    }
    if operation_id is not None:
        output["operation_id"] = operation_id
    return output


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        init_db()
        store = EncryptedDatabaseSecretStore(load_secret_store_configuration())
        with SessionLocal() as session:
            if args.command == "status":
                names = [args.integration] if args.integration else list(INSTALLATION_INTEGRATIONS)
                output: object = [_safe_status(store, session, name) for name in names]
            else:
                output = _mutate(store, session, args)
        print(json.dumps(output, sort_keys=True))
        return 0
    except (SecretStoreError, SQLAlchemyError) as exc:
        if isinstance(exc, SQLAlchemyError):
            code = "INSTALLATION_SECRET_OPERATION_FAILED"
        else:
            code = str(exc)
        if code not in {
            "SECRET_NOT_FOUND", "SECRET_REVOKED", "SECRET_OPERATION_CONFLICT",
            "SECRET_CONCURRENT_MODIFICATION", "SECRET_STORE_DISABLED",
            "SECRET_STORE_UNAVAILABLE", "SECRET_SCOPE_INVALID",
            "SECRET_MATERIAL_INVALID", "SECRET_KEYRING_INVALID",
        }:
            code = "INSTALLATION_SECRET_OPERATION_FAILED"
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
