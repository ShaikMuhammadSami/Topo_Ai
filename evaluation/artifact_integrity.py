from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import re
import stat
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EVALUATION_ARTIFACT_INTEGRITY_VERSION = "evaluation-artifact-integrity-v1"
INTEGRITY_MANIFEST_FILENAME = "artifact-integrity-v1.json"
HASH_ALGORITHM = "sha256"
PATH_NORMALIZATION = "relative-posix-nfc-v1"
PATH_ORDERING = "utf8-byte-lexicographic"
CANONICAL_JSON_SERIALIZATION = "utf8-json-sorted-keys-compact-lf-v1"

OS_METADATA_EXCLUDED = (
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
)

FORBIDDEN_TRANSIENT_SUFFIXES = (
    ".tmp",
    ".temp",
    ".swp",
    ".swo",
    ".partial",
    ".lock",
    "-wal",
    "-shm",
    "-journal",
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ENTRY_KEYS = frozenset({"path", "sha256", "size_bytes"})
_MATERIAL_KEYS = frozenset(
    {
        "algorithm",
        "contract",
        "entries",
        "ordering",
        "path_normalization",
        "scope",
        "serialization",
    }
)
_MANIFEST_KEYS = _MATERIAL_KEYS | {"tree_sha256"}


class ArtifactIntegrityError(Exception):
    """Base class for deterministic EAI-1 generation and verification errors."""

    code = "artifact_integrity_error"


class InvalidRootError(ArtifactIntegrityError):
    code = "invalid_root"


class TransientTreeError(ArtifactIntegrityError):
    code = "transient_tree"


class UnsupportedLinkError(ArtifactIntegrityError):
    code = "unsupported_link"


class UnsupportedFileTypeError(ArtifactIntegrityError):
    code = "unsupported_file_type"


class MissingManifestError(ArtifactIntegrityError):
    code = "missing_manifest"


class MalformedManifestError(ArtifactIntegrityError):
    code = "malformed_manifest"


class UnsupportedVersionError(ArtifactIntegrityError):
    code = "unsupported_version"


class CanonicalPathError(ArtifactIntegrityError):
    code = "invalid_canonical_path"


class CanonicalPathCollisionError(ArtifactIntegrityError):
    code = "canonical_path_collision"


class FileSetMismatchError(ArtifactIntegrityError):
    code = "file_set_mismatch"

    def __init__(
        self,
        *,
        missing_paths: Sequence[str] = (),
        unexpected_paths: Sequence[str] = (),
    ) -> None:
        self.missing_paths = tuple(missing_paths)
        self.unexpected_paths = tuple(unexpected_paths)
        super().__init__(
            "Integrity file set mismatch: "
            f"missing={list(self.missing_paths)}, "
            f"unexpected={list(self.unexpected_paths)}"
        )


class ContentMismatchError(ArtifactIntegrityError):
    code = "content_mismatch"

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Integrity content mismatch for {path}: {reason}")


class TreeDigestMismatchError(ArtifactIntegrityError):
    code = "tree_digest_mismatch"


class ManifestWriteError(ArtifactIntegrityError):
    code = "manifest_write_error"


@dataclass(frozen=True)
class IntegrityVerification:
    contract: str
    tree_sha256: str
    included_file_count: int
    manifest_path: str = INTEGRITY_MANIFEST_FILENAME
    verified: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "included_file_count": self.included_file_count,
            "manifest_path": self.manifest_path,
            "tree_sha256": self.tree_sha256,
            "verified": self.verified,
        }


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize EAI-1 material as compact sorted UTF-8 JSON plus one LF."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size_bytes += len(chunk)
    except OSError as exc:
        raise InvalidRootError("A scoped file could not be read.") from exc
    return digest.hexdigest(), size_bytes


def normalize_relative_path(value: str) -> str:
    """Return one safe relative POSIX/NFC path or fail closed."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CanonicalPathError("Integrity paths must be non-empty text.")
    if ntpath.splitdrive(value)[0]:
        raise CanonicalPathError("Drive-qualified integrity paths are forbidden.")
    normalized_separators = value.replace("\\", "/")
    if normalized_separators.startswith("/"):
        raise CanonicalPathError("Absolute integrity paths are forbidden.")
    raw_parts = normalized_separators.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise CanonicalPathError(
            "Integrity paths cannot contain empty, current, or parent segments."
        )
    parts = tuple(unicodedata.normalize("NFC", part) for part in raw_parts)
    return "/".join(parts)


def canonicalize_relative_paths(values: Iterable[str]) -> tuple[str, ...]:
    """Normalize, collision-check, and UTF-8-byte sort relative paths."""
    canonical_to_source: dict[str, str] = {}
    for value in values:
        canonical = normalize_relative_path(value)
        existing = canonical_to_source.get(canonical)
        if existing is not None and existing != value:
            raise CanonicalPathCollisionError(
                f"Canonical path collision for {canonical}."
            )
        if existing is not None:
            raise CanonicalPathCollisionError(
                f"Duplicate canonical path for {canonical}."
            )
        canonical_to_source[canonical] = value
    return tuple(sorted(canonical_to_source, key=lambda item: item.encode("utf-8")))


def _canonical_filesystem_path(relative: Path) -> str:
    normalized_parts: list[str] = []
    for part in relative.parts:
        if part in {"", ".", ".."} or "/" in part or "\\" in part:
            raise CanonicalPathError("A filesystem path cannot be represented safely.")
        normalized_parts.append(unicodedata.normalize("NFC", part))
    if not normalized_parts:
        raise CanonicalPathError("The logical result root is not a file path.")
    return "/".join(normalized_parts)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _validate_root(root: Path | str) -> Path:
    candidate = Path(root)
    try:
        metadata = candidate.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise InvalidRootError("The evaluation result root does not exist.") from exc
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
        raise UnsupportedLinkError("The evaluation result root cannot be a link.")
    if not stat.S_ISDIR(metadata.st_mode):
        raise InvalidRootError("The evaluation result root must be a directory.")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise InvalidRootError("The evaluation result root cannot be resolved.") from exc


def _is_forbidden_transient(canonical_path: str) -> bool:
    name = canonical_path.rsplit("/", 1)[-1].lower()
    return any(name.endswith(suffix) for suffix in FORBIDDEN_TRANSIENT_SUFFIXES)


def _collect_entries(root: Path) -> tuple[dict[str, Any], ...]:
    canonical_to_native: dict[str, Path] = {}

    def visit(directory: Path) -> None:
        try:
            children = tuple(os.scandir(directory))
        except OSError as exc:
            raise InvalidRootError("A scoped directory could not be enumerated.") from exc
        for child in children:
            path = Path(child.path)
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise InvalidRootError("A scoped path could not be inspected.") from exc
            relative = path.relative_to(root)
            canonical = _canonical_filesystem_path(relative)
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                raise UnsupportedLinkError(
                    f"Links are unsupported in finalized result trees: {canonical}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                visit(path)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise UnsupportedFileTypeError(
                    f"Unsupported non-regular result artifact: {canonical}"
                )
            if canonical == INTEGRITY_MANIFEST_FILENAME:
                continue
            if canonical.rsplit("/", 1)[-1] in OS_METADATA_EXCLUDED:
                continue
            if _is_forbidden_transient(canonical):
                raise TransientTreeError(
                    f"Finalized result tree contains transient state: {canonical}"
                )
            existing = canonical_to_native.get(canonical)
            if existing is not None and existing != path:
                raise CanonicalPathCollisionError(
                    f"Canonical path collision for {canonical}."
                )
            canonical_to_native[canonical] = path

    visit(root)
    entries: list[dict[str, Any]] = []
    for canonical in sorted(canonical_to_native, key=lambda item: item.encode("utf-8")):
        digest, size_bytes = _hash_file(canonical_to_native[canonical])
        entries.append(
            {
                "path": canonical,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
    return tuple(entries)


def _scope_contract() -> dict[str, Any]:
    return {
        "included": "all_regular_files_recursive",
        "links": "unsupported_symlink_or_reparse_point",
        "manifest_excluded": INTEGRITY_MANIFEST_FILENAME,
        "os_metadata_excluded": list(OS_METADATA_EXCLUDED),
        "root": ".",
        "transient_files": {
            "policy": "forbidden",
            "suffixes": list(FORBIDDEN_TRANSIENT_SUFFIXES),
        },
    }


def _tree_material(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "algorithm": HASH_ALGORITHM,
        "contract": EVALUATION_ARTIFACT_INTEGRITY_VERSION,
        "entries": list(entries),
        "ordering": PATH_ORDERING,
        "path_normalization": PATH_NORMALIZATION,
        "scope": _scope_contract(),
        "serialization": CANONICAL_JSON_SERIALIZATION,
    }


def _tree_digest(material: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(material))


def build_integrity_manifest(root: Path | str) -> dict[str, Any]:
    """Build an EAI-1 manifest in memory without modifying the result tree."""
    resolved_root = _validate_root(root)
    material = _tree_material(_collect_entries(resolved_root))
    return {**material, "tree_sha256": _tree_digest(material)}


def _temporary_manifest_path(root: Path) -> Path:
    return root / f".{INTEGRITY_MANIFEST_FILENAME}.tmp"


def write_integrity_manifest(root: Path | str) -> dict[str, Any]:
    """Atomically write a deterministic EAI-1 manifest at the result root."""
    resolved_root = _validate_root(root)
    manifest = build_integrity_manifest(resolved_root)
    output_path = resolved_root / INTEGRITY_MANIFEST_FILENAME
    temporary_path = _temporary_manifest_path(resolved_root)
    data = canonical_json_bytes(manifest)
    try:
        with temporary_path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    except OSError as exc:
        raise ManifestWriteError("The integrity manifest could not be written.") from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return manifest


def _validate_manifest_structure(manifest: Any, raw_bytes: bytes) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise MalformedManifestError("The integrity manifest must be a JSON object.")
    if manifest.get("contract") != EVALUATION_ARTIFACT_INTEGRITY_VERSION:
        raise UnsupportedVersionError("Unsupported artifact-integrity contract version.")
    if frozenset(manifest) != _MANIFEST_KEYS:
        raise MalformedManifestError("The integrity manifest fields are not canonical.")
    expected_metadata = _tree_material(())
    for key in _MATERIAL_KEYS - {"entries"}:
        if manifest.get(key) != expected_metadata[key]:
            raise MalformedManifestError(
                f"The integrity manifest has invalid {key} metadata."
            )
    tree_sha256 = manifest.get("tree_sha256")
    if not isinstance(tree_sha256, str) or not _SHA256_PATTERN.fullmatch(tree_sha256):
        raise MalformedManifestError("tree_sha256 must be lowercase SHA-256 hex.")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise MalformedManifestError("Manifest entries must be a JSON array.")
    entries: list[dict[str, Any]] = []
    paths: list[str] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or frozenset(raw_entry) != _ENTRY_KEYS:
            raise MalformedManifestError("Every manifest entry must use the EAI-1 schema.")
        path = raw_entry.get("path")
        if not isinstance(path, str):
            raise MalformedManifestError("Every manifest path must be text.")
        canonical = normalize_relative_path(path)
        if canonical != path:
            raise CanonicalPathError("Manifest paths must already be canonical.")
        digest = raw_entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise MalformedManifestError("Entry SHA-256 must be lowercase hexadecimal.")
        size_bytes = raw_entry.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise MalformedManifestError("Entry size_bytes must be a non-negative integer.")
        paths.append(path)
        entries.append(
            {"path": path, "sha256": digest, "size_bytes": size_bytes}
        )
    canonical_order = canonicalize_relative_paths(paths)
    if tuple(paths) != canonical_order:
        raise MalformedManifestError("Manifest entries are not in canonical path order.")
    if raw_bytes != canonical_json_bytes(manifest):
        raise MalformedManifestError("The integrity manifest JSON is not canonical.")
    return {**manifest, "entries": entries}


def verify_integrity_manifest(root: Path | str) -> IntegrityVerification:
    """Verify an EAI-1 manifest against an independently scanned result tree."""
    resolved_root = _validate_root(root)
    manifest_path = resolved_root / INTEGRITY_MANIFEST_FILENAME
    try:
        manifest_metadata = manifest_path.lstat()
    except FileNotFoundError as exc:
        raise MissingManifestError("The EAI-1 integrity manifest is missing.") from exc
    except OSError as exc:
        raise MalformedManifestError(
            "The EAI-1 integrity manifest cannot be inspected."
        ) from exc
    if stat.S_ISLNK(manifest_metadata.st_mode) or _is_reparse_point(manifest_metadata):
        raise UnsupportedLinkError("The EAI-1 integrity manifest cannot be a link.")
    if not stat.S_ISREG(manifest_metadata.st_mode):
        raise MissingManifestError("The EAI-1 integrity manifest is missing.")
    try:
        raw_bytes = manifest_path.read_bytes()
        decoded = raw_bytes.decode("utf-8")
        loaded = json.loads(decoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedManifestError("The integrity manifest is not valid UTF-8 JSON.") from exc
    manifest = _validate_manifest_structure(loaded, raw_bytes)
    current_entries = _collect_entries(resolved_root)
    manifest_by_path = {entry["path"]: entry for entry in manifest["entries"]}
    current_by_path = {entry["path"]: entry for entry in current_entries}
    missing = tuple(
        sorted(set(manifest_by_path) - set(current_by_path), key=str.encode)
    )
    unexpected = tuple(
        sorted(set(current_by_path) - set(manifest_by_path), key=str.encode)
    )
    if missing or unexpected:
        raise FileSetMismatchError(
            missing_paths=missing,
            unexpected_paths=unexpected,
        )
    for path in sorted(manifest_by_path, key=lambda item: item.encode("utf-8")):
        expected = manifest_by_path[path]
        actual = current_by_path[path]
        if expected["size_bytes"] != actual["size_bytes"]:
            raise ContentMismatchError(path, "size mismatch")
        if expected["sha256"].lower() != actual["sha256"].lower():
            raise ContentMismatchError(path, "SHA-256 mismatch")
    material = {key: manifest[key] for key in _MATERIAL_KEYS}
    calculated_tree_sha256 = _tree_digest(material)
    if calculated_tree_sha256.lower() != manifest["tree_sha256"].lower():
        raise TreeDigestMismatchError("The manifest tree SHA-256 does not match its material.")
    independently_built = _tree_material(current_entries)
    if _tree_digest(independently_built).lower() != manifest["tree_sha256"].lower():
        raise TreeDigestMismatchError("The current result tree identity does not match.")
    return IntegrityVerification(
        contract=EVALUATION_ARTIFACT_INTEGRITY_VERSION,
        tree_sha256=manifest["tree_sha256"],
        included_file_count=len(current_entries),
    )


def _print_success(
    *,
    state: str,
    contract: str,
    tree_sha256: str,
    included_file_count: int,
) -> None:
    print(f"contract={contract}")
    print(f"tree_sha256={tree_sha256}")
    print(f"included_files={included_file_count}")
    print(f"manifest={INTEGRITY_MANIFEST_FILENAME}")
    print(f"verification={state}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify a deterministic EAI-1 result-tree identity."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate":
            manifest = write_integrity_manifest(arguments.root)
            _print_success(
                state="generated",
                contract=manifest["contract"],
                tree_sha256=manifest["tree_sha256"],
                included_file_count=len(manifest["entries"]),
            )
        else:
            verification = verify_integrity_manifest(arguments.root)
            _print_success(
                state="valid",
                contract=verification.contract,
                tree_sha256=verification.tree_sha256,
                included_file_count=verification.included_file_count,
            )
    except ArtifactIntegrityError as exc:
        print("verification=failed", file=sys.stderr)
        print(f"error_code={exc.code}", file=sys.stderr)
        print(f"message={exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
