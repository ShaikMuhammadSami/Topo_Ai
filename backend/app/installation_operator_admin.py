"""Local deployment-operator authority for exact principal-ID assignments."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal, init_db
from app.db.schema_management import SchemaAuthorityError
from app.models.principal_identity import is_valid_principal_id
from app.services.authority_assignments import (
    AuthorityAssignmentError,
    disable_installation_operator,
    get_installation_operator_status,
    grant_installation_operator,
)
from app.services.principal_identity import PrincipalIdentityError


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid arguments\n")


def _principal_id(value: str) -> str:
    if not is_valid_principal_id(value):
        raise argparse.ArgumentTypeError("invalid principal ID")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="python -m app.installation_operator_admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "grant", "disable"):
        operation = subparsers.add_parser(command)
        operation.add_argument("principal_id", type=_principal_id)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        init_db()
        with SessionLocal() as session:
            if args.command == "grant":
                grant_installation_operator(session, principal_id=args.principal_id)
            elif args.command == "disable":
                disable_installation_operator(session, principal_id=args.principal_id)
            result = get_installation_operator_status(session, principal_id=args.principal_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PrincipalIdentityError, AuthorityAssignmentError, SQLAlchemyError, SchemaAuthorityError) as exc:
        code = str(exc) if isinstance(exc, (PrincipalIdentityError, AuthorityAssignmentError)) else ""
        if isinstance(exc, SchemaAuthorityError):
            code = "INSTALLATION_OPERATOR_SCHEMA_UNAVAILABLE"
        if code not in {"PRINCIPAL_NOT_PROVISIONED", "PRINCIPAL_TYPE_MISMATCH", "INSTALLATION_ASSIGNMENT_INVALID", "INSTALLATION_OPERATOR_SCHEMA_UNAVAILABLE"}:
            code = "INSTALLATION_OPERATOR_OPERATION_FAILED"
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
