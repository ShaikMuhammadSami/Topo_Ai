from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.db.database import engine
from app.db.schema_management import (
    SchemaAuthorityError,
    adopt_current_schema,
    inspect_schema_authority,
)


def _print_report(report) -> None:
    current = ",".join(report.current_revisions) or "none"
    print(f"expected_head={report.expected_head}")
    print(f"current_revision={current}")
    print(f"revision_match={'yes' if report.revision_matches else 'no'}")
    print(f"schema_parity={'exact' if report.schema_matches else 'drift'}")
    for difference in report.differences:
        print(f"drift={difference.render()}")


def verify() -> int:
    with engine.connect() as connection:
        report = inspect_schema_authority(connection)
    _print_report(report)
    return 0 if report.ok else 1


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
    except SchemaAuthorityError as exc:
        print(f"error={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
