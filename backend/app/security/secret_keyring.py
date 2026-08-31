"""Operator-mounted root keys. Never generate a fallback or consult provider env."""

import base64
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from app.models.secret_store import INSTALLATION_PATTERN, KEY_ID_PATTERN, SecretStoreError

MAX_KEYRING_BYTES = 65536
MAX_ROOT_KEYS = 32


class SecretKeyring:
    __slots__ = ("__keys", "active_key_id")

    def __init__(self, keys: dict[str, bytes], active_key_id: str):
        if (
            not isinstance(keys, dict) or not 1 <= len(keys) <= MAX_ROOT_KEYS
            or any(not isinstance(k, str) or not KEY_ID_PATTERN.fullmatch(k)
                   or not isinstance(v, bytes) or len(v) != 32 for k, v in keys.items())
        ):
            raise SecretStoreError("SECRET_KEYRING_INVALID")
        if not isinstance(active_key_id, str) or active_key_id not in keys:
            raise SecretStoreError("SECRET_ACTIVE_KEY_MISSING")
        self.__keys = MappingProxyType(dict(keys))
        self.active_key_id = active_key_id

    def key(self, key_id: str) -> bytes:
        if key_id not in self.__keys:
            raise SecretStoreError("SECRET_REQUIRED_KEY_MISSING")
        return self.__keys[key_id]

    def contains(self, key_id: str) -> bool:
        return key_id in self.__keys

    def __repr__(self):
        return f"SecretKeyring(count={len(self.__keys)})"

    __str__ = __repr__


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def load_keyring(path: str, active_key_id: str) -> SecretKeyring:
    """Bounded, non-symlink regular file; POSIX restrictive mode required.

    Windows development is supported, but this is NOT Windows ACL validation.
    Symlink ancestors/reparse points are refused as well as symlink leaves.
    """
    try:
        candidate = Path(path)
        if not path or not candidate.is_absolute():
            raise ValueError()
        for part in (candidate, *candidate.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError()
        before = candidate.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_KEYRING_BYTES:
            raise ValueError()
        if os.name == "posix" and before.st_mode & 0o077:
            raise ValueError()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(candidate, flags), "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ValueError()
            if os.name == "posix" and opened.st_mode & 0o077:
                raise ValueError()
            data = handle.read(MAX_KEYRING_BYTES + 1)
        if not data or len(data) > MAX_KEYRING_BYTES:
            raise ValueError()
        document = json.loads(data, object_pairs_hook=_unique_object)
        if not isinstance(document, dict) or set(document) != {"version", "keys"}:
            raise ValueError()
        if type(document["version"]) is not int or document["version"] != 1:
            raise ValueError()
        values = document["keys"]
        if not isinstance(values, dict) or not 1 <= len(values) <= MAX_ROOT_KEYS:
            raise ValueError()
        keys = {}
        for key_id, encoded in values.items():
            if not isinstance(encoded, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded):
                raise ValueError()
            raw = base64.b64decode(encoded.rstrip("=") + "=", altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(raw).decode().rstrip("=") != encoded.rstrip("="):
                raise ValueError()
            keys[key_id] = raw
        return SecretKeyring(keys, active_key_id)
    except SecretStoreError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    # Raise outside the handler: no raw JSON/path/decoder exception chain.
    raise SecretStoreError("SECRET_KEYRING_INVALID")


@dataclass(frozen=True)
class SecretStoreConfiguration:
    backend: str = "disabled"
    keyring: SecretKeyring | None = field(default=None, repr=False)
    installation_id: str | None = None

    def __post_init__(self):
        if self.backend not in {"disabled", "encrypted_db"}:
            raise SecretStoreError("SECRET_STORE_CONFIGURATION_INVALID")
        if self.backend == "encrypted_db" and not isinstance(self.keyring, SecretKeyring):
            raise SecretStoreError("SECRET_KEYRING_INVALID")
        if self.installation_id is not None and not INSTALLATION_PATTERN.fullmatch(self.installation_id):
            raise SecretStoreError("SECRET_SCOPE_INVALID")


def load_secret_store_configuration() -> SecretStoreConfiguration:
    backend = os.environ.get("TOPO_SECRET_STORE_BACKEND", "disabled")
    keyring = None
    if backend == "encrypted_db":
        keyring = load_keyring(
            os.environ.get("TOPO_SECRET_KEYRING_FILE", ""),
            os.environ.get("TOPO_SECRET_ACTIVE_KEY_ID", ""),
        )
    return SecretStoreConfiguration(backend, keyring, os.environ.get("TOPO_INSTALLATION_ID"))
