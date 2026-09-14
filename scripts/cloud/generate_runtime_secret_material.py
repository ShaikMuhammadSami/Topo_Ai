"""Generate TopoAI's initial non-database runtime secret material.

This operator utility deliberately delegates format and digest validation to
the production authentication and SecretStore contracts. It never creates a
Kubernetes Secret and never prints generated values.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
from typing import Iterator, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if os.fspath(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(BACKEND_ROOT))

from app.models.principal_identity import validate_identity_authority
from app.models.secret_store import KEY_ID_PATTERN, SecretStoreError
from app.security.api_tokens import token_digest
from app.security.auth_config import (
    AuthConfigurationError,
    TOKEN_REGISTRY_ENV,
    load_token_registry,
)
from app.security.secret_keyring import load_keyring


BOOTSTRAP_TOKEN_FILE = "bootstrap-token.txt"
BOOTSTRAP_REGISTRY_FILE = "bootstrap-token-hashes.json"
SECRET_KEYRING_FILE = "secret-store-keyring.json"
ACTIVE_KEY_ID_FILE = "secret-store-active-key-id.txt"
OUTPUT_FILENAMES = (
    BOOTSTRAP_TOKEN_FILE,
    BOOTSTRAP_REGISTRY_FILE,
    SECRET_KEYRING_FILE,
    ACTIVE_KEY_ID_FILE,
)

BOOTSTRAP_TOKEN_ENTROPY_BYTES = 48
SECRET_STORE_ROOT_KEY_BYTES = 32
DEFAULT_KEY_ID = "runtime-v1"


class MaterialGenerationError(RuntimeError):
    """Bounded operator error that never contains generated material."""


@dataclass(frozen=True)
class GenerationResult:
    output_directory: Path
    filenames: tuple[str, ...]
    active_key_id: str


@contextmanager
def _temporary_registry(raw_registry: str) -> Iterator[None]:
    previous = os.environ.get(TOKEN_REGISTRY_ENV)
    os.environ[TOKEN_REGISTRY_ENV] = raw_registry
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(TOKEN_REGISTRY_ENV, None)
        else:
            os.environ[TOKEN_REGISTRY_ENV] = previous


def _validate_metadata(
    *, subject: str, display_name: str | None, roles: Sequence[str], key_id: str
) -> tuple[str, tuple[str, ...]]:
    try:
        validate_identity_authority(subject, field_name="subject")
        if subject.lower() == "unknown":
            raise ValueError()
        resolved_display_name = display_name if display_name is not None else subject
        validate_identity_authority(
            resolved_display_name,
            field_name="display_name",
        )
    except (TypeError, ValueError) as exc:
        raise MaterialGenerationError("INVALID_BOOTSTRAP_IDENTITY") from exc

    normalized_roles = tuple(roles)
    if (
        not normalized_roles
        or any(
            not isinstance(role, str)
            or not role
            or role != role.strip()
            for role in normalized_roles
        )
        or len(set(normalized_roles)) != len(normalized_roles)
    ):
        raise MaterialGenerationError("INVALID_BOOTSTRAP_ROLES")
    if not isinstance(key_id, str) or KEY_ID_PATTERN.fullmatch(key_id) is None:
        raise MaterialGenerationError("INVALID_SECRET_STORE_KEY_ID")
    return resolved_display_name, normalized_roles


def _resolve_output_directory(value: str | os.PathLike[str]) -> Path:
    try:
        requested = Path(value).expanduser()
        resolved = requested.resolve(strict=False)
        repository = REPOSITORY_ROOT.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise MaterialGenerationError("OUTPUT_DIRECTORY_INVALID") from exc
    if resolved == repository or resolved.is_relative_to(repository):
        raise MaterialGenerationError("OUTPUT_DIRECTORY_INSIDE_REPOSITORY")
    return resolved


def _prepare_output_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir():
            raise OSError()
        if os.name == "posix":
            path.chmod(0o700)
    except OSError as exc:
        raise MaterialGenerationError("OUTPUT_DIRECTORY_UNAVAILABLE") from exc


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_material(
    *,
    output_directory: Path,
    bootstrap_token: str,
    bootstrap_registry: bytes,
    root_key: bytes,
    keyring: bytes,
    active_key_id: str,
) -> None:
    staging_path: Path | None = None
    try:
        registry_text = bootstrap_registry.decode("utf-8")
        with _temporary_registry(registry_text):
            parsed_registry = load_token_registry()
        digest = token_digest(bootstrap_token)
        if digest not in parsed_registry or len(parsed_registry) != 1:
            raise MaterialGenerationError("BOOTSTRAP_REGISTRY_VALIDATION_FAILED")

        handle, raw_path = tempfile.mkstemp(
            prefix=".topo-keyring-",
            suffix=".tmp",
            dir=output_directory,
        )
        staging_path = Path(raw_path)
        with os.fdopen(handle, "wb") as stream:
            stream.write(keyring)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "posix":
            staging_path.chmod(0o600)

        parsed_keyring = load_keyring(os.fspath(staging_path), active_key_id)
        if (
            not parsed_keyring.contains(active_key_id)
            or parsed_keyring.key(active_key_id) != root_key
            or len(parsed_keyring.key(active_key_id)) != SECRET_STORE_ROOT_KEY_BYTES
        ):
            raise MaterialGenerationError("SECRET_KEYRING_VALIDATION_FAILED")
    except MaterialGenerationError:
        raise
    except (AuthConfigurationError, SecretStoreError, OSError, UnicodeError) as exc:
        raise MaterialGenerationError("GENERATED_MATERIAL_VALIDATION_FAILED") from exc
    finally:
        if staging_path is not None:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass


def _exclusive_write(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "posix":
            path.chmod(0o600)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def generate_runtime_secret_material(
    *,
    output_directory: str | os.PathLike[str],
    subject: str,
    display_name: str | None,
    roles: Sequence[str],
    key_id: str = DEFAULT_KEY_ID,
) -> GenerationResult:
    """Generate, self-validate, and exclusively persist one material set."""
    resolved_display_name, normalized_roles = _validate_metadata(
        subject=subject,
        display_name=display_name,
        roles=roles,
        key_id=key_id,
    )
    destination = _resolve_output_directory(output_directory)
    _prepare_output_directory(destination)

    targets = {name: destination / name for name in OUTPUT_FILENAMES}
    if any(path.exists() or path.is_symlink() for path in targets.values()):
        raise MaterialGenerationError("OUTPUT_MATERIAL_ALREADY_EXISTS")

    bootstrap_token = secrets.token_urlsafe(BOOTSTRAP_TOKEN_ENTROPY_BYTES)
    root_key = secrets.token_bytes(SECRET_STORE_ROOT_KEY_BYTES)
    digest = token_digest(bootstrap_token)
    bootstrap_registry = _json_bytes(
        {
            digest: {
                "display_name": resolved_display_name,
                "roles": list(normalized_roles),
                "subject": subject,
            }
        }
    )
    encoded_root_key = base64.urlsafe_b64encode(root_key).decode("ascii").rstrip("=")
    keyring = _json_bytes(
        {"keys": {key_id: encoded_root_key}, "version": 1}
    )

    _validate_material(
        output_directory=destination,
        bootstrap_token=bootstrap_token,
        bootstrap_registry=bootstrap_registry,
        root_key=root_key,
        keyring=keyring,
        active_key_id=key_id,
    )

    content = {
        BOOTSTRAP_TOKEN_FILE: bootstrap_token.encode("utf-8"),
        BOOTSTRAP_REGISTRY_FILE: bootstrap_registry,
        SECRET_KEYRING_FILE: keyring,
        ACTIVE_KEY_ID_FILE: key_id.encode("utf-8"),
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

    return GenerationResult(destination, OUTPUT_FILENAMES, key_id)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate validated initial TopoAI bootstrap-token and SecretStore "
            "material without printing secret values."
        )
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Secure destination outside the TopoAI Git worktree.",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Stable, non-secret bootstrap human subject; no tenant ID is inferred.",
    )
    parser.add_argument(
        "--display-name",
        help="Non-secret display name; defaults to the stable subject.",
    )
    parser.add_argument(
        "--role",
        dest="roles",
        action="append",
        required=True,
        help=(
            "Legacy bootstrap role metadata. Repeat for each role; this does not "
            "create PH-5 permission assignments."
        ),
    )
    parser.add_argument(
        "--key-id",
        default=DEFAULT_KEY_ID,
        help="Non-secret SecretStore key identifier (default: runtime-v1).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = generate_runtime_secret_material(
            output_directory=arguments.output_dir,
            subject=arguments.subject,
            display_name=arguments.display_name,
            roles=arguments.roles,
            key_id=arguments.key_id,
        )
    except MaterialGenerationError as exc:
        print(f"Runtime secret material was not created: {exc}", file=sys.stderr)
        return 1

    print("Runtime secret material created and validated.")
    print(f"Destination: {result.output_directory}")
    print("Files:")
    for filename in result.filenames:
        print(f"  {filename}")
    print(f"Active key ID: {result.active_key_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
