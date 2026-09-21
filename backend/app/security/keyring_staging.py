"""Stage a projected SecretStore keyring into an owner-only runtime file."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from app.security.secret_keyring import MAX_KEYRING_BYTES

SOURCE_KEYRING_PATH = Path("/var/run/secrets/topo/keyring-source/keyring.json")
STAGED_KEYRING_PATH = Path("/run/topo/keyring/keyring.json")
STAGING_ERROR_CODE = "KEYRING_STAGE_FAILED"


class KeyringStagingError(RuntimeError):
    """Bounded staging failure that never contains key material or paths."""


def _read_bounded(source: Path) -> bytes:
    with source.open("rb") as stream:
        payload = stream.read(MAX_KEYRING_BYTES + 1)
    if not payload or len(payload) > MAX_KEYRING_BYTES:
        raise ValueError()
    return payload


def _validate_destination(metadata: os.stat_result) -> None:
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError()
    if os.name == "posix" and (
        metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError()


def stage_keyring(source: Path, destination: Path) -> None:
    """Copy exact bounded bytes to a newly created owner-only regular file."""
    created = False
    descriptor: int | None = None
    try:
        payload = _read_bounded(source)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(destination, flags, 0o600)
        created = True
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        else:
            os.chmod(destination, 0o600)
        _validate_destination(os.fstat(descriptor))
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_destination(destination.lstat())
    # Any staging failure must remove a file created by this invocation and
    # cross the boundary only as one bounded, non-secret failure code.
    except Exception:  # noqa: BLE001
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise KeyringStagingError(STAGING_ERROR_CODE) from None


def main() -> int:
    try:
        stage_keyring(SOURCE_KEYRING_PATH, STAGED_KEYRING_PATH)
    # Suppress all unexpected details because filesystem errors can contain
    # operator paths and staging must fail closed without emitting them.
    except Exception:  # noqa: BLE001
        print("KEYRING_STAGE=FAIL", file=sys.stderr)
        return 1
    print("KEYRING_STAGE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
