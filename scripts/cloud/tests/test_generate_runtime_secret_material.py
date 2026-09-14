from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from uuid import uuid4

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = (
    REPOSITORY_ROOT / "scripts/cloud/generate_runtime_secret_material.py"
)
SPEC = importlib.util.spec_from_file_location(
    "generate_runtime_secret_material",
    GENERATOR_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load runtime secret material generator.")
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)

from app.security.api_tokens import token_digest
from app.security.auth_config import TOKEN_REGISTRY_ENV, load_token_registry
from app.security.secret_keyring import load_keyring


def _outside_directory(tmp_path: Path, name: str = "material") -> Path:
    assert not tmp_path.resolve().is_relative_to(REPOSITORY_ROOT.resolve())
    return tmp_path / name


def _generate(tmp_path: Path, name: str = "material"):
    return GENERATOR.generate_runtime_secret_material(
        output_directory=_outside_directory(tmp_path, name),
        subject="operator:cloud-bootstrap",
        display_name="Cloud Bootstrap Operator",
        roles=("admin", "operator"),
    )


def _read_material(result) -> dict[str, bytes]:
    return {
        filename: (result.output_directory / filename).read_bytes()
        for filename in result.filenames
    }


def test_generated_material_round_trips_through_production_contracts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _generate(tmp_path)
    material = _read_material(result)
    token = material[GENERATOR.BOOTSTRAP_TOKEN_FILE].decode("utf-8")
    registry_text = material[GENERATOR.BOOTSTRAP_REGISTRY_FILE].decode("utf-8")
    monkeypatch.setenv(TOKEN_REGISTRY_ENV, registry_text)

    registry = load_token_registry()
    digest = token_digest(token)
    assert set(registry) == {digest}
    assert registry[digest].subject == "operator:cloud-bootstrap"
    assert registry[digest].display_name == "Cloud Bootstrap Operator"
    assert registry[digest].roles == ("admin", "operator")

    active_key_id = material[GENERATOR.ACTIVE_KEY_ID_FILE].decode("utf-8")
    keyring = load_keyring(
        os.fspath(result.output_directory / GENERATOR.SECRET_KEYRING_FILE),
        active_key_id,
    )
    assert keyring.contains(active_key_id)
    assert len(keyring.key(active_key_id)) == GENERATOR.SECRET_STORE_ROOT_KEY_BYTES

    encoded = json.loads(
        material[GENERATOR.SECRET_KEYRING_FILE]
    )["keys"][active_key_id]
    decoded = base64.urlsafe_b64decode(encoded + "=")
    assert decoded == keyring.key(active_key_id)
    assert len(decoded) == 32


def test_two_generations_have_independent_token_and_root_key_material(
    tmp_path: Path,
) -> None:
    first = _read_material(_generate(tmp_path, "first"))
    second = _read_material(_generate(tmp_path, "second"))

    assert first[GENERATOR.BOOTSTRAP_TOKEN_FILE] != second[GENERATOR.BOOTSTRAP_TOKEN_FILE]
    assert first[GENERATOR.BOOTSTRAP_REGISTRY_FILE] != second[GENERATOR.BOOTSTRAP_REGISTRY_FILE]
    assert first[GENERATOR.SECRET_KEYRING_FILE] != second[GENERATOR.SECRET_KEYRING_FILE]


def test_generator_uses_secrets_randomness_with_required_sizes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def token_urlsafe(size: int) -> str:
        calls.append(("token", size))
        return "generated-" + ("t" * 64)

    def token_bytes(size: int) -> bytes:
        calls.append(("key", size))
        return bytes(range(size))

    monkeypatch.setattr(GENERATOR.secrets, "token_urlsafe", token_urlsafe)
    monkeypatch.setattr(GENERATOR.secrets, "token_bytes", token_bytes)

    _generate(tmp_path)

    assert calls == [
        ("token", GENERATOR.BOOTSTRAP_TOKEN_ENTROPY_BYTES),
        ("key", GENERATOR.SECRET_STORE_ROOT_KEY_BYTES),
    ]


def test_output_inside_repository_is_rejected_without_creating_it() -> None:
    destination = REPOSITORY_ROOT / f"c2a0-output-must-not-exist-{uuid4()}"

    with pytest.raises(
        GENERATOR.MaterialGenerationError,
        match="^OUTPUT_DIRECTORY_INSIDE_REPOSITORY$",
    ):
        GENERATOR.generate_runtime_secret_material(
            output_directory=destination,
            subject="operator:cloud-bootstrap",
            display_name=None,
            roles=("admin",),
        )

    assert not destination.exists()


def test_preexisting_material_is_never_overwritten(tmp_path: Path) -> None:
    destination = _outside_directory(tmp_path)
    destination.mkdir()
    protected = destination / GENERATOR.BOOTSTRAP_TOKEN_FILE
    marker = b"preexisting-non-secret-test-marker"
    protected.write_bytes(marker)

    with pytest.raises(
        GENERATOR.MaterialGenerationError,
        match="^OUTPUT_MATERIAL_ALREADY_EXISTS$",
    ):
        _generate(tmp_path)

    assert protected.read_bytes() == marker
    assert {path.name for path in destination.iterdir()} == {
        GENERATOR.BOOTSTRAP_TOKEN_FILE
    }


def test_console_output_never_contains_generated_values(
    tmp_path: Path,
    capsys,
) -> None:
    destination = _outside_directory(tmp_path)
    result = GENERATOR.main(
        (
            "--output-dir",
            os.fspath(destination),
            "--subject",
            "operator:cloud-bootstrap",
            "--display-name",
            "Cloud Bootstrap Operator",
            "--role",
            "admin",
        )
    )
    captured = capsys.readouterr()
    material = {
        path.name: path.read_text(encoding="utf-8")
        for path in destination.iterdir()
    }
    token = material[GENERATOR.BOOTSTRAP_TOKEN_FILE]
    encoded_key = json.loads(material[GENERATOR.SECRET_KEYRING_FILE])["keys"][
        GENERATOR.DEFAULT_KEY_ID
    ]

    assert result == 0
    assert token not in captured.out
    assert token not in captured.err
    assert encoded_key not in captured.out
    assert encoded_key not in captured.err
    assert material[GENERATOR.BOOTSTRAP_REGISTRY_FILE] not in captured.out
    assert material[GENERATOR.SECRET_KEYRING_FILE] not in captured.out


def test_partial_write_failure_cleans_created_files_and_claims_no_success(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    destination = _outside_directory(tmp_path)
    original = GENERATOR._exclusive_write
    calls = 0

    def fail_second(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic write failure")
        original(path, content)

    monkeypatch.setattr(GENERATOR, "_exclusive_write", fail_second)
    result = GENERATOR.main(
        (
            "--output-dir",
            os.fspath(destination),
            "--subject",
            "operator:cloud-bootstrap",
            "--role",
            "admin",
        )
    )
    captured = capsys.readouterr()

    assert result == 1
    assert "created and validated" not in captured.out
    assert "OUTPUT_MATERIAL_WRITE_FAILED" in captured.err
    assert list(destination.iterdir()) == []


def test_generation_produces_only_four_nonempty_non_manifest_files(
    tmp_path: Path,
) -> None:
    result = _generate(tmp_path)
    paths = list(result.output_directory.iterdir())

    assert {path.name for path in paths} == set(GENERATOR.OUTPUT_FILENAMES)
    assert len(paths) == 4
    assert all(path.stat().st_size > 0 for path in paths)
    assert not any(path.suffix in {".yaml", ".yml"} for path in paths)
    if os.name == "posix":
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths)


def test_invalid_identity_roles_and_key_id_fail_before_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        GENERATOR.secrets,
        "token_urlsafe",
        lambda _: pytest.fail("randomness used before metadata validation"),
    )
    cases = (
        {"subject": "unknown", "roles": ("admin",), "key_id": "runtime-v1"},
        {"subject": "operator:valid", "roles": (), "key_id": "runtime-v1"},
        {"subject": "operator:valid", "roles": ("admin",), "key_id": "invalid key"},
    )
    for index, case in enumerate(cases):
        with pytest.raises(GENERATOR.MaterialGenerationError):
            GENERATOR.generate_runtime_secret_material(
                output_directory=_outside_directory(tmp_path, f"case-{index}"),
                display_name=None,
                **case,
            )
