from __future__ import annotations

import argparse
from collections.abc import Sequence
from enum import IntEnum

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import engine
from app.db.schema_management import (
    MultipleMigrationHeadsError,
    SchemaAuthorityError,
    SchemaAuthorityState,
    adopt_current_schema,
    inspect_schema_authority,
)


class SchemaAdminExitCode(IntEnum):
    CURRENT = 0
    REVISION_MISSING = 10
    REVISION_BEHIND = 11
    REVISION_AHEAD_OR_UNKNOWN = 12
    MULTIPLE_HEADS = 13
    SCHEMA_DRIFT = 14
    CONNECTION_ERROR = 15
    AUTHORITY_ERROR = 16


_STATE_EXIT_CODES = {
    SchemaAuthorityState.CURRENT: SchemaAdminExitCode.CURRENT,
    SchemaAuthorityState.REVISION_MISSING: SchemaAdminExitCode.REVISION_MISSING,
    SchemaAuthorityState.REVISION_BEHIND: SchemaAdminExitCode.REVISION_BEHIND,
    SchemaAuthorityState.REVISION_AHEAD_OR_UNKNOWN: (
        SchemaAdminExitCode.REVISION_AHEAD_OR_UNKNOWN
    ),
    SchemaAuthorityState.MULTIPLE_HEADS: SchemaAdminExitCode.MULTIPLE_HEADS,
    SchemaAuthorityState.SCHEMA_DRIFT: SchemaAdminExitCode.SCHEMA_DRIFT,
}


def _print_report(report) -> None:
    current = ",".join(report.current_revisions) or "none"
    print(f"state={report.state.value}")
    print(f"expected_head={report.expected_head}")
    print(f"migration_head_count={report.migration_head_count}")
    print(f"current_revision_count={len(report.current_revisions)}")
    print(f"current_revision={current}")
    print(f"revision_match={'yes' if report.revision_matches else 'no'}")
    print(f"schema_parity={'exact' if report.schema_matches else 'drift'}")
    for difference in report.differences:
        print(f"drift_category={difference.kind}")
        print(f"drift={difference.render()}")


def verify() -> int:
    with engine.connect() as connection:
        report = inspect_schema_authority(connection)
    _print_report(report)
    return int(_STATE_EXIT_CODES[report.state])


def adopt_current() -> int:
    with engine.begin() as connection:
        before = inspect_schema_authority(connection)
        _print_report(before)
        adopted = adopt_current_schema(connection)
    _print_report(adopted)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify or explicitly adopt Topo's current database schema."
    )
    parser.add_argument("command", choices=("verify", "adopt-current"))
    args = parser.parse_args(argv)

    try:
        if args.command == "verify":
            return verify()
        return adopt_current()
    except MultipleMigrationHeadsError as exc:
        print("state=MULTIPLE_HEADS")
        print(f"migration_head_count={exc.head_count}")
        print(f"error={exc}")
        return int(SchemaAdminExitCode.MULTIPLE_HEADS)
    except SchemaAuthorityError as exc:
        print(f"error={exc}")
        return int(SchemaAdminExitCode.AUTHORITY_ERROR)
    except SQLAlchemyError:
        # Never render DBAPI exceptions: they can contain credential-bearing URLs.
        print("state=CONNECTION_ERROR")
        print("error=database connection failed")
        return int(SchemaAdminExitCode.CONNECTION_ERROR)


if __name__ == "__main__":
    raise SystemExit(main())
