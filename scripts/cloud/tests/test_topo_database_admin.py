from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ADMIN_PATH = REPOSITORY_ROOT / "scripts/cloud/topo_database_admin.py"
SPEC = importlib.util.spec_from_file_location("topo_database_admin", ADMIN_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load database administration utility.")
ADMIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ADMIN
SPEC.loader.exec_module(ADMIN)


def _write_secret_directory(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    directory = tmp_path / "bootstrap"
    directory.mkdir()
    values = {
        "database-host": "database.cluster.example",
        "database-port": "5432",
        "database-name": "topo",
        "master-username": "bootstrap_admin",
        "master-password": "master-test-value-never-log",
        "topo-app-password": "app-test-value-" + ("a" * 40),
        "topo-migrator-password": "migrator-test-value-" + ("b" * 40),
    }
    for key, value in values.items():
        (directory / key).write_text(value, encoding="utf-8")
    return directory, values


def test_bootstrap_settings_are_loaded_only_from_exact_secret_files(
    tmp_path: Path,
) -> None:
    directory, values = _write_secret_directory(tmp_path)

    settings = ADMIN.load_bootstrap_settings(directory)

    assert settings.host == values["database-host"]
    assert settings.port == 5432
    assert settings.database == values["database-name"]
    assert settings.master_username == values["master-username"]
    assert settings.master_password == values["master-password"]
    assert settings.app_password == values["topo-app-password"]
    assert settings.migrator_password == values["topo-migrator-password"]
    rendered = repr(settings)
    assert values["master-password"] not in rendered
    assert values["topo-app-password"] not in rendered
    assert values["topo-migrator-password"] not in rendered


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("database-port", "0"),
        ("database-port", "65536"),
        ("database-host", " host.example"),
        ("database-name", "topo\nother"),
        ("topo-app-password", "short"),
        ("topo-migrator-password", "short"),
    ),
)
def test_invalid_secret_material_fails_with_one_bounded_code(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    directory, _ = _write_secret_directory(tmp_path)
    (directory / key).write_text(value, encoding="utf-8")

    with pytest.raises(
        ADMIN.DatabaseAdminError,
        match="^BOOTSTRAP_SECRET_INVALID$",
    ):
        ADMIN.load_bootstrap_settings(directory)


def test_role_password_is_composed_as_scram_verifier_not_raw_password(
    monkeypatch,
) -> None:
    raw_password = "raw-role-password-must-not-enter-sql"
    verifier = "SCRAM-SHA-256$4096:test-salt$stored-key:server-key"

    class PgConnection:
        def __init__(self) -> None:
            self.info = type("Info", (), {"encoding": "utf-8"})()
            self.pgconn = self
            self.encrypt_calls: list[tuple[bytes, bytes, bytes]] = []

        def encrypt_password(
            self,
            password: bytes,
            role: bytes,
            algorithm: bytes,
        ) -> bytes:
            self.encrypt_calls.append((password, role, algorithm))
            return verifier.encode("utf-8")

    class Cursor:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement, parameters=None) -> None:
            rendered = (
                statement.as_string(None)
                if hasattr(statement, "as_string")
                else str(statement)
            )
            self.statements.append(rendered)

    connection = PgConnection()
    cursor = Cursor()
    monkeypatch.setattr(ADMIN, "_role_exists", lambda *_: True)
    monkeypatch.setattr(ADMIN, "_remove_role_memberships", lambda *_: None)

    ADMIN._converge_role(
        connection,
        cursor,
        role_name=ADMIN.APP_ROLE,
        password=raw_password,
    )

    sql_text = "\n".join(cursor.statements)
    assert raw_password not in sql_text
    assert verifier in sql_text
    assert "NOSUPERUSER" in sql_text
    assert "NOCREATEDB" in sql_text
    assert "NOCREATEROLE" in sql_text
    assert "NOREPLICATION" in sql_text
    assert "NOBYPASSRLS" in sql_text
    assert connection.encrypt_calls == [
        (
            raw_password.encode("utf-8"),
            ADMIN.APP_ROLE.encode("utf-8"),
            b"scram-sha-256",
        )
    ]


def test_cli_failure_never_echoes_driver_or_secret_material(
    monkeypatch,
    capsys,
) -> None:
    secret = "driver-error-contained-a-secret"

    def fail(_):
        raise RuntimeError(secret)

    monkeypatch.setattr(ADMIN, "load_bootstrap_settings", fail)

    result = ADMIN.main(("bootstrap", "--secret-dir", "C:/safe/absolute/path"))
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "Topo database administration failed safely."
    assert secret not in captured.err


def test_connection_contract_always_requires_tls_and_bounded_timeouts() -> None:
    options = ADMIN._connection_options()

    assert options["sslmode"] == "require"
    assert options["connect_timeout"] == ADMIN.CONNECT_TIMEOUT_SECONDS
    assert (
        f"statement_timeout={ADMIN.STATEMENT_TIMEOUT_MILLISECONDS}"
        in options["options"]
    )
    assert "lock_timeout=" in options["options"]
