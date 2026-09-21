from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from app.security import keyring_staging
from app.security.keyring_staging import KeyringStagingError, stage_keyring
from app.security.secret_keyring import MAX_KEYRING_BYTES


def test_stage_keyring_preserves_exact_bytes_in_new_regular_file(
    tmp_path: Path,
) -> None:
    payload = bytes(range(256)) + os.urandom(257)
    source = tmp_path / "projected-keyring.json"
    destination = tmp_path / "staged" / "keyring.json"
    destination.parent.mkdir()
    source.write_bytes(payload)

    stage_keyring(source, destination)

    metadata = destination.lstat()
    assert destination.read_bytes() == payload
    assert stat.S_ISREG(metadata.st_mode)
    assert not stat.S_ISLNK(metadata.st_mode)
    if os.name == "posix":
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert metadata.st_uid == os.geteuid()


@pytest.mark.parametrize(
    "payload",
    [b"", b"x" * (MAX_KEYRING_BYTES + 1)],
    ids=("empty", "oversized"),
)
def test_stage_keyring_rejects_empty_or_oversized_source(
    tmp_path: Path,
    payload: bytes,
) -> None:
    source = tmp_path / "projected-keyring.json"
    destination = tmp_path / "staged-keyring.json"
    source.write_bytes(payload)

    with pytest.raises(KeyringStagingError, match="^KEYRING_STAGE_FAILED$"):
        stage_keyring(source, destination)

    assert not destination.exists()


def test_stage_keyring_rejects_existing_destination_without_replacing_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "projected-keyring.json"
    destination = tmp_path / "staged-keyring.json"
    source.write_bytes(b"new-keyring-bytes")
    destination.write_bytes(b"existing-file-must-remain")

    with pytest.raises(KeyringStagingError, match="^KEYRING_STAGE_FAILED$"):
        stage_keyring(source, destination)

    assert destination.read_bytes() == b"existing-file-must-remain"


def test_keyring_staging_cli_logs_only_bounded_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "key-identifier-and-material-must-not-be-logged"

    def fail(*_: object) -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr(keyring_staging, "stage_keyring", fail)

    assert keyring_staging.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "KEYRING_STAGE=FAIL"
    assert secret not in captured.err


def test_keyring_staging_cli_uses_fixed_paths_and_bounded_success_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = b'{"version":1,"keys":{"synthetic":"not-real-key-material"}}'
    source = tmp_path / "projected-keyring.json"
    destination = tmp_path / "staged-keyring.json"
    source.write_bytes(payload)
    monkeypatch.setattr(keyring_staging, "SOURCE_KEYRING_PATH", source)
    monkeypatch.setattr(keyring_staging, "STAGED_KEYRING_PATH", destination)

    assert keyring_staging.main() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "KEYRING_STAGE=PASS"
    assert captured.err == ""
    assert payload not in captured.out.encode()
    assert destination.read_bytes() == payload
