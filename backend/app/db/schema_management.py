from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import Constraint, Index, Table


BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = BACKEND_DIR / "alembic.ini"


class SchemaAuthorityError(RuntimeError):
    """The database does not satisfy Topo's migration authority contract."""


@dataclass(frozen=True, order=True)
class SchemaDifference:
    kind: str
    table: str = ""
    object_name: str = ""
    detail: str = ""

    def render(self) -> str:
        location = ".".join(
            value for value in (self.table, self.object_name) if value
        )
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.kind}{f' {location}' if location else ''}{suffix}"


@dataclass(frozen=True)
class SchemaVerification:
    expected_head: str
    current_revisions: tuple[str, ...]
    differences: tuple[SchemaDifference, ...]

    @property
    def revision_matches(self) -> bool:
        return self.current_revisions == (self.expected_head,)

    @property
    def schema_matches(self) -> bool:
        return not self.differences

    @property
    def ok(self) -> bool:
        return self.revision_matches and self.schema_matches


def alembic_config(
    *,
    database_url: str | None = None,
    connection: Connection | None = None,
) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    if database_url is not None:
        # ConfigParser treats percent signs as interpolation markers.
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def expected_head() -> str:
    heads = tuple(script_directory().get_heads())
    if len(heads) != 1:
        raise SchemaAuthorityError(
            "Topo requires exactly one Alembic head; "
            f"found {len(heads)}."
        )
    return heads[0]


def current_revisions(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(connection)
    return tuple(sorted(context.get_current_heads()))


def _name(value: Any) -> str:
    return str(value) if value is not None else "<unnamed>"


def _table_name(value: Any) -> str:
    table = getattr(value, "table", None)
    return _name(getattr(table, "name", ""))


def _column_names(value: Any) -> str:
    columns = getattr(value, "columns", ())
    return ",".join(_name(getattr(column, "name", column)) for column in columns)


def _normalize_autogenerate_item(item: Any) -> Iterable[SchemaDifference]:
    if isinstance(item, list):
        for nested in item:
            yield from _normalize_autogenerate_item(nested)
        return

    kind = _name(item[0])
    if kind in {"add_table", "remove_table"}:
        table: Table = item[1]
        yield SchemaDifference(kind=kind, table=_name(table.name))
        return

    if kind in {"add_column", "remove_column"}:
        column = item[3]
        yield SchemaDifference(
            kind=kind,
            table=_name(item[2]),
            object_name=_name(column.name),
            detail=str(column.type),
        )
        return

    if kind in {"add_index", "remove_index"}:
        index: Index = item[1]
        yield SchemaDifference(
            kind=kind,
            table=_table_name(index),
            object_name=_name(index.name),
            detail=(
                f"columns={_column_names(index)}; unique={bool(index.unique)}"
            ),
        )
        return

    if kind in {
        "add_constraint",
        "remove_constraint",
        "add_fk",
        "remove_fk",
    }:
        constraint: Constraint = item[1]
        yield SchemaDifference(
            kind=kind,
            table=_table_name(constraint),
            object_name=_name(constraint.name),
            detail=(
                f"type={type(constraint).__name__}; "
                f"columns={_column_names(constraint)}"
            ),
        )
        return

    if kind.startswith("modify_"):
        old_value = item[-2]
        new_value = item[-1]
        yield SchemaDifference(
            kind=kind,
            table=_name(item[2]),
            object_name=_name(item[3]),
            detail=f"database={old_value}; metadata={new_value}",
        )
        return

    yield SchemaDifference(kind=kind, detail="unrecognized schema difference")


def _primary_key_differences(
    connection: Connection,
    metadata: MetaData,
) -> Iterable[SchemaDifference]:
    inspector = inspect(connection)
    database_tables = set(inspector.get_table_names())
    for table_name in sorted(set(metadata.tables) & database_tables):
        expected = tuple(
            column.name for column in metadata.tables[table_name].primary_key.columns
        )
        actual = tuple(
            (inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
        )
        if actual != expected:
            yield SchemaDifference(
                kind="modify_primary_key",
                table=table_name,
                detail=(
                    f"database={','.join(actual)}; metadata={','.join(expected)}"
                ),
            )


def schema_differences(
    connection: Connection,
    *,
    metadata: MetaData | None = None,
) -> tuple[SchemaDifference, ...]:
    if metadata is None:
        from app.db import models  # noqa: F401
        from app.db.database import Base

        metadata = Base.metadata

    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": True,
            "target_metadata": metadata,
        },
    )
    differences = [
        difference
        for item in compare_metadata(context, metadata)
        for difference in _normalize_autogenerate_item(item)
    ]
    differences.extend(_primary_key_differences(connection, metadata))
    return tuple(sorted(set(differences)))


def inspect_schema_authority(connection: Connection) -> SchemaVerification:
    return SchemaVerification(
        expected_head=expected_head(),
        current_revisions=current_revisions(connection),
        differences=schema_differences(connection),
    )


def adopt_current_schema(connection: Connection) -> SchemaVerification:
    before = inspect_schema_authority(connection)
    if before.current_revisions:
        raise SchemaAuthorityError(
            "Adoption refused: the database already has Alembic revision state."
        )
    if not before.schema_matches:
        raise SchemaAuthorityError(
            "Adoption refused: the existing schema is not an exact match."
        )

    command.stamp(alembic_config(connection=connection), before.expected_head)
    after = inspect_schema_authority(connection)
    if not after.ok:
        raise SchemaAuthorityError(
            "Adoption did not produce the expected revision state."
        )
    return after


def verify_database_revision(bind: Engine) -> None:
    expected = expected_head()
    with bind.connect() as connection:
        revisions = current_revisions(connection)

    if revisions == (expected,):
        return

    if not revisions:
        state = "missing"
    elif len(revisions) > 1:
        state = "multiple"
    else:
        try:
            known = script_directory().get_revision(revisions[0]) is not None
        except CommandError:
            known = False
        state = "behind" if known else "ahead-or-unknown"
    displayed = ", ".join(revisions) if revisions else "none"
    raise SchemaAuthorityError(
        "Database Alembic revision verification failed "
        f"(state={state}, current={displayed}, expected={expected}). "
        "Run the reviewed deployment migration before starting Topo."
    )
