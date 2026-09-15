from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = REPOSITORY_ROOT / "scripts/cloud/generate_database_role_material.py"
SPEC = importlib.util.spec_from_file_location(
    "generate_database_role_material",
    GENERATOR_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load database role material generator.")
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


def _outside_directory(tmp_path: Path, name: str = "database-material") -> Path:
    assert not tmp_path.resolve().is_relative_to(REPOSITORY_ROOT.resolve())
    return tmp_path / name


def _generate(tmp_path: Path, name: str = "database-material"):
    return GENERATOR.generate_database_role_material(
        output_directory=_outside_directory(tmp_path, name),
        host="topo-test.cluster.example",
        port=5432,
        database="topo",
    )


def test_generated_roles_are_distinct_and_urls_round_trip_safely(
    tmp_path: Path,
) -> None:
    result = _generate(tmp_path)
    app_password = (result.output_directory / GENERATOR.APP_PASSWORD_FILE).read_text()
    migrator_password = (
        result.output_directory / GENERATOR.MIGRATOR_PASSWORD_FILE
    ).read_text()
    app_url = make_url(
        (result.output_directory / GENERATOR.APP_DATABASE_URL_FILE).read_text()
    )
    migrator_url = make_url(
        (result.output_directory / GENERATOR.MIGRATOR_DATABASE_URL_FILE).read_text()
    )

    assert app_password != migrator_password
    assert len(app_password) >= 64
    assert len(migrator_password) >= 64
    for parsed, username, password in (
        (app_url, GENERATOR.APP_ROLE, app_password),
        (migrator_url, GENERATOR.MIGRATOR_ROLE, migrator_password),
    ):
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.username == username
        assert parsed.password == password
        assert parsed.host == "topo-test.cluster.example"
        assert parsed.port == 5432
        assert parsed.database == "topo"
        assert parsed.query == {"sslmode": "require"}


def test_generator_uses_cryptographic_randomness_for_each_role(
    tmp_path: Path,
    monkeypatch,
) -> None:
    values = iter(("a" * 64, "b" * 64))
    calls: list[int] = []

    def token_urlsafe(size: int) -> str:
        calls.append(size)
        return next(values)

    monkeypatch.setattr(GENERATOR.secrets, "token_urlsafe", token_urlsafe)
    result = _generate(tmp_path)

    assert calls == [
        GENERATOR.PASSWORD_ENTROPY_BYTES,
        GENERATOR.PASSWORD_ENTROPY_BYTES,
    ]
    assert (
        result.output_directory / GENERATOR.APP_PASSWORD_FILE
    ).read_text() == "a" * 64
    assert (
        result.output_directory / GENERATOR.MIGRATOR_PASSWORD_FILE
    ).read_text() == "b" * 64


def test_output_inside_repository_is_rejected_without_creating_it() -> None:
    destination = REPOSITORY_ROOT / f"c2a1-output-must-not-exist-{uuid4()}"

    with pytest.raises(
        GENERATOR.MaterialGenerationError,
        match="^OUTPUT_DIRECTORY_INSIDE_REPOSITORY$",
    ):
        GENERATOR.generate_database_role_material(
            output_directory=destination,
            host="topo-test.cluster.example",
            port=5432,
            database="topo",
        )

    assert not destination.exists()


def test_preexisting_material_is_never_overwritten(tmp_path: Path) -> None:
    destination = _outside_directory(tmp_path)
    destination.mkdir()
    protected = destination / GENERATOR.APP_PASSWORD_FILE
    marker = b"preexisting-non-secret-test-marker"
    protected.write_bytes(marker)

    with pytest.raises(
        GENERATOR.MaterialGenerationError,
        match="^OUTPUT_MATERIAL_ALREADY_EXISTS$",
    ):
        _generate(tmp_path)

    assert protected.read_bytes() == marker
    assert {path.name for path in destination.iterdir()} == {
        GENERATOR.APP_PASSWORD_FILE
    }


def test_console_output_never_contains_passwords_or_urls(
    tmp_path: Path,
    capsys,
) -> None:
    destination = _outside_directory(tmp_path)
    result = GENERATOR.main(
        (
            "--output-dir",
            os.fspath(destination),
            "--db-host",
            "topo-test.cluster.example",
            "--db-port",
            "5432",
            "--db-name",
            "topo",
        )
    )
    captured = capsys.readouterr()
    sensitive = [
        (destination / filename).read_text() for filename in GENERATOR.OUTPUT_FILENAMES
    ]

    assert result == 0
    assert all(value not in captured.out for value in sensitive)
    assert all(value not in captured.err for value in sensitive)
    assert "topo_app:" not in captured.out
    assert "topo_migrator:" not in captured.out


def test_partial_write_failure_removes_every_new_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    destination = _outside_directory(tmp_path)
    original = GENERATOR._exclusive_write
    calls = 0

    def fail_third(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic write failure")
        original(path, content)

    monkeypatch.setattr(GENERATOR, "_exclusive_write", fail_third)
    result = GENERATOR.main(
        (
            "--output-dir",
            os.fspath(destination),
            "--db-host",
            "topo-test.cluster.example",
            "--db-name",
            "topo",
        )
    )
    captured = capsys.readouterr()

    assert result == 1
    assert "created and validated" not in captured.out
    assert "OUTPUT_MATERIAL_WRITE_FAILED" in captured.err
    assert list(destination.iterdir()) == []


def test_generation_produces_only_four_non_manifest_files(tmp_path: Path) -> None:
    result = _generate(tmp_path)
    paths = list(result.output_directory.iterdir())

    assert {path.name for path in paths} == set(GENERATOR.OUTPUT_FILENAMES)
    assert len(paths) == 4
    assert all(path.stat().st_size > 0 for path in paths)
    assert not any(path.suffix in {".yaml", ".yml"} for path in paths)
    if os.name == "posix":
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths)


@pytest.mark.parametrize(
    ("host", "port", "database"),
    (
        ("", 5432, "topo"),
        (" host", 5432, "topo"),
        ("host", 0, "topo"),
        ("host", 65536, "topo"),
        ("host", 5432, ""),
        ("host", 5432, "topo\nother"),
    ),
)
def test_invalid_endpoint_is_rejected_before_randomness(
    tmp_path: Path,
    monkeypatch,
    host: str,
    port: int,
    database: str,
) -> None:
    monkeypatch.setattr(
        GENERATOR.secrets,
        "token_urlsafe",
        lambda _: pytest.fail("randomness used before endpoint validation"),
    )
    with pytest.raises(
        GENERATOR.MaterialGenerationError,
        match="^DATABASE_ENDPOINT_INVALID$",
    ):
        GENERATOR.generate_database_role_material(
            output_directory=_outside_directory(tmp_path),
            host=host,
            port=port,
            database=database,
        )
