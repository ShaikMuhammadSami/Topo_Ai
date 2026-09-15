"""Generate dedicated PostgreSQL role passwords and TLS database URLs."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL, make_url

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIRECTORY))

from generate_runtime_secret_material import (  # noqa: I001
    MaterialGenerationError,
    _exclusive_write,
    _prepare_output_directory,
    _resolve_output_directory,
)


APP_ROLE = "topo_app"
MIGRATOR_ROLE = "topo_migrator"
PASSWORD_ENTROPY_BYTES = 48
APP_PASSWORD_FILE = "topo-app-password.txt"
MIGRATOR_PASSWORD_FILE = "topo-migrator-password.txt"
APP_DATABASE_URL_FILE = "database-url.txt"
MIGRATOR_DATABASE_URL_FILE = "migration-database-url.txt"
OUTPUT_FILENAMES = (
    APP_PASSWORD_FILE,
    MIGRATOR_PASSWORD_FILE,
    APP_DATABASE_URL_FILE,
    MIGRATOR_DATABASE_URL_FILE,
)


@dataclass(frozen=True)
class DatabaseMaterialResult:
    output_directory: Path
    filenames: tuple[str, ...]


def _validated_endpoint(host: str, port: int, database: str) -> tuple[str, int, str]:
    if (
        not host
        or host != host.strip()
        or not database
        or database != database.strip()
        or any(ord(character) < 32 for character in host + database)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
    ):
        raise MaterialGenerationError("DATABASE_ENDPOINT_INVALID")
    return host, port, database


def _database_url(
    *, host: str, port: int, database: str, username: str, password: str
) -> str:
    return URL.create(
        "postgresql",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"sslmode": "require"},
    ).render_as_string(hide_password=False)


def generate_database_role_material(
    *,
    output_directory: str | os.PathLike[str],
    host: str,
    port: int,
    database: str,
) -> DatabaseMaterialResult:
    host, port, database = _validated_endpoint(host, port, database)
    destination = _resolve_output_directory(output_directory)
    _prepare_output_directory(destination)
    targets = {name: destination / name for name in OUTPUT_FILENAMES}
    if any(path.exists() or path.is_symlink() for path in targets.values()):
        raise MaterialGenerationError("OUTPUT_MATERIAL_ALREADY_EXISTS")

    app_password = secrets.token_urlsafe(PASSWORD_ENTROPY_BYTES)
    migrator_password = secrets.token_urlsafe(PASSWORD_ENTROPY_BYTES)
    if app_password == migrator_password:
        raise MaterialGenerationError("DATABASE_PASSWORD_COLLISION")
    app_url = _database_url(
        host=host,
        port=port,
        database=database,
        username=APP_ROLE,
        password=app_password,
    )
    migrator_url = _database_url(
        host=host,
        port=port,
        database=database,
        username=MIGRATOR_ROLE,
        password=migrator_password,
    )

    for value, username, password in (
        (app_url, APP_ROLE, app_password),
        (migrator_url, MIGRATOR_ROLE, migrator_password),
    ):
        parsed = make_url(value)
        if (
            parsed.get_backend_name() != "postgresql"
            or parsed.username != username
            or parsed.password != password
            or parsed.host != host
            or parsed.port != port
            or parsed.database != database
            or parsed.query.get("sslmode") != "require"
        ):
            raise MaterialGenerationError("DATABASE_URL_VALIDATION_FAILED")

    content = {
        APP_PASSWORD_FILE: app_password.encode("utf-8"),
        MIGRATOR_PASSWORD_FILE: migrator_password.encode("utf-8"),
        APP_DATABASE_URL_FILE: app_url.encode("utf-8"),
        MIGRATOR_DATABASE_URL_FILE: migrator_url.encode("utf-8"),
    }
    created: list[Path] = []
    try:
        for filename in OUTPUT_FILENAMES:
            _exclusive_write(targets[filename], content[filename])
            created.append(targets[filename])
    except OSError as exc:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise MaterialGenerationError("OUTPUT_MATERIAL_WRITE_FAILED") from exc
    return DatabaseMaterialResult(destination, OUTPUT_FILENAMES)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate distinct topo_app/topo_migrator passwords and validated "
            "TLS-required PostgreSQL URLs without printing their values."
        )
    )
    parser.add_argument(
        "--output-dir", required=True, help="Secure directory outside Git."
    )
    parser.add_argument(
        "--db-host", required=True, help="Non-secret RDS endpoint hostname."
    )
    parser.add_argument("--db-port", type=int, default=5432, help="Database port.")
    parser.add_argument(
        "--db-name", required=True, help="TopoAI PostgreSQL database name."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = generate_database_role_material(
            output_directory=arguments.output_dir,
            host=arguments.db_host,
            port=arguments.db_port,
            database=arguments.db_name,
        )
    except MaterialGenerationError as exc:
        print(f"Database role material was not created: {exc}", file=sys.stderr)
        return 1
    print("Database role material created and validated.")
    print(f"Destination: {result.output_directory}")
    print("Files:")
    for filename in result.filenames:
        print(f"  {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
