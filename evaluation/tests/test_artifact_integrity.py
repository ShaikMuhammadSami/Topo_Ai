from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import evaluation.artifact_integrity as integrity
from evaluation.artifact_integrity import (
    CANONICAL_JSON_SERIALIZATION,
    EVALUATION_ARTIFACT_INTEGRITY_VERSION,
    FORBIDDEN_TRANSIENT_SUFFIXES,
    HASH_ALGORITHM,
    INTEGRITY_MANIFEST_FILENAME,
    OS_METADATA_EXCLUDED,
    PATH_NORMALIZATION,
    PATH_ORDERING,
    CanonicalPathCollisionError,
    CanonicalPathError,
    ContentMismatchError,
    FileSetMismatchError,
    InvalidRootError,
    MalformedManifestError,
    ManifestWriteError,
    MissingManifestError,
    TransientTreeError,
    TreeDigestMismatchError,
    UnsupportedLinkError,
    UnsupportedVersionError,
    build_integrity_manifest,
    canonical_json_bytes,
    canonicalize_relative_paths,
    main,
    normalize_relative_path,
    verify_integrity_manifest,
    write_integrity_manifest,
)


def write_file(root: Path, relative: str, content: bytes = b"content") -> Path:
    path = root / Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def manifest_path(root: Path) -> Path:
    return root / INTEGRITY_MANIFEST_FILENAME


def load_manifest(root: Path) -> dict:
    return json.loads(manifest_path(root).read_text(encoding="utf-8"))


def rewrite_manifest(root: Path, value: dict) -> None:
    manifest_path(root).write_bytes(canonical_json_bytes(value))


def create_symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink creation is unavailable: {exc}")


def test_one_file_result_root_builds_and_verifies(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json", b'{"ok":true}\n')
    manifest = write_integrity_manifest(tmp_path)
    result = verify_integrity_manifest(tmp_path)

    assert manifest["contract"] == EVALUATION_ARTIFACT_INTEGRITY_VERSION
    assert result.verified is True
    assert result.included_file_count == 1
    assert result.tree_sha256 == manifest["tree_sha256"]


def test_empty_result_root_has_a_valid_zero_entry_identity(tmp_path: Path) -> None:
    manifest = write_integrity_manifest(tmp_path)

    assert manifest["entries"] == []
    assert verify_integrity_manifest(tmp_path).included_file_count == 0


def test_nested_regular_files_are_included_recursively(tmp_path: Path) -> None:
    write_file(tmp_path, "root.txt", b"root")
    write_file(tmp_path, "a/b/c.bin", b"nested")

    manifest = build_integrity_manifest(tmp_path)

    assert [entry["path"] for entry in manifest["entries"]] == [
        "a/b/c.bin",
        "root.txt",
    ]


def test_manifest_freezes_contract_and_algorithm_metadata(tmp_path: Path) -> None:
    manifest = build_integrity_manifest(tmp_path)

    assert manifest["contract"] == EVALUATION_ARTIFACT_INTEGRITY_VERSION
    assert manifest["algorithm"] == HASH_ALGORITHM == "sha256"
    assert manifest["path_normalization"] == PATH_NORMALIZATION
    assert manifest["ordering"] == PATH_ORDERING
    assert manifest["serialization"] == CANONICAL_JSON_SERIALIZATION


def test_manifest_scope_uses_logical_root_not_absolute_path(tmp_path: Path) -> None:
    manifest = build_integrity_manifest(tmp_path)
    serialized = canonical_json_bytes(manifest).decode("utf-8")

    assert manifest["scope"]["root"] == "."
    assert str(tmp_path.resolve()) not in serialized
    assert tmp_path.name not in serialized


def test_sha256_digests_are_lowercase_hex(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin", b"abc")
    manifest = build_integrity_manifest(tmp_path)

    digests = [manifest["tree_sha256"], manifest["entries"][0]["sha256"]]
    assert all(len(value) == 64 for value in digests)
    assert all(value == value.lower() for value in digests)
    assert all(set(value) <= set("0123456789abcdef") for value in digests)


def test_backslash_input_normalizes_to_forward_slash() -> None:
    assert normalize_relative_path(r"nested\result.json") == "nested/result.json"


def test_nested_manifest_paths_use_forward_slashes(tmp_path: Path) -> None:
    write_file(tmp_path, "nested/deeper/result.json")
    path = build_integrity_manifest(tmp_path)["entries"][0]["path"]

    assert path == "nested/deeper/result.json"
    assert "\\" not in path


@pytest.mark.parametrize(
    "value",
    (
        "../outside.json",
        "inside/../outside.json",
        "./result.json",
        "nested//result.json",
    ),
)
def test_parent_current_and_empty_segments_are_rejected(value: str) -> None:
    with pytest.raises(CanonicalPathError):
        normalize_relative_path(value)


@pytest.mark.parametrize(
    "value",
    (
        "/absolute/result.json",
        r"\absolute\result.json",
        r"C:\absolute\result.json",
        "C:drive-relative.json",
        r"\\server\share\result.json",
    ),
)
def test_absolute_and_drive_qualified_paths_are_rejected(value: str) -> None:
    with pytest.raises(CanonicalPathError):
        normalize_relative_path(value)


def test_unicode_paths_use_nfc_normalization() -> None:
    decomposed = "cafe\u0301/result.json"
    composed = "caf\u00e9/result.json"

    assert normalize_relative_path(decomposed) == composed


def test_unicode_normalization_collision_fails_closed() -> None:
    with pytest.raises(CanonicalPathCollisionError):
        canonicalize_relative_paths(("cafe\u0301.json", "caf\u00e9.json"))


def test_duplicate_manifest_path_fails_closed() -> None:
    with pytest.raises(CanonicalPathCollisionError):
        canonicalize_relative_paths(("same.json", "same.json"))


def test_scanned_canonical_path_collision_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_file(tmp_path, "first.json")
    write_file(tmp_path, "second.json")
    monkeypatch.setattr(integrity, "_canonical_filesystem_path", lambda _: "same.json")

    with pytest.raises(CanonicalPathCollisionError):
        build_integrity_manifest(tmp_path)


def test_utf8_byte_lexicographic_order_is_explicit(tmp_path: Path) -> None:
    for relative in ("z.json", "\u00e9.json", "a.json"):
        write_file(tmp_path, relative)
    paths = [entry["path"] for entry in build_integrity_manifest(tmp_path)["entries"]]

    assert paths == sorted(paths, key=lambda item: item.encode("utf-8"))


def test_creation_order_does_not_change_entries_manifest_or_tree_digest(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    files = (("z/result.bin", b"z"), ("a/result.bin", b"a"), ("m.txt", b"m"))
    for relative, content in files:
        write_file(root_a, relative, content)
    for relative, content in reversed(files):
        write_file(root_b, relative, content)

    manifest_a = write_integrity_manifest(root_a)
    manifest_b = write_integrity_manifest(root_b)

    assert manifest_a["entries"] == manifest_b["entries"]
    assert manifest_a["tree_sha256"] == manifest_b["tree_sha256"]
    assert manifest_path(root_a).read_bytes() == manifest_path(root_b).read_bytes()


def test_file_digest_hashes_exact_raw_bytes(tmp_path: Path) -> None:
    content = b"\x00\xffraw\r\nbytes"
    write_file(tmp_path, "artifact.bin", content)
    entry = build_integrity_manifest(tmp_path)["entries"][0]

    assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert entry["size_bytes"] == len(content)


def test_lf_and_crlf_are_distinct_file_and_tree_identities(tmp_path: Path) -> None:
    lf_root = tmp_path / "lf"
    crlf_root = tmp_path / "crlf"
    lf_root.mkdir()
    crlf_root.mkdir()
    lf = build_integrity_manifest(write_file(lf_root, "text.txt", b"a\nb\n").parent)
    crlf = build_integrity_manifest(
        write_file(crlf_root, "text.txt", b"a\r\nb\r\n").parent
    )

    assert lf["entries"][0]["sha256"] != crlf["entries"][0]["sha256"]
    assert lf["tree_sha256"] != crlf["tree_sha256"]


def test_one_byte_mutation_changes_file_and_tree_hash_and_restore_recovers(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "artifact.bin", b"abc")
    original = build_integrity_manifest(tmp_path)
    path.write_bytes(b"abd")
    changed = build_integrity_manifest(tmp_path)
    path.write_bytes(b"abc")
    restored = build_integrity_manifest(tmp_path)

    assert changed["entries"][0]["sha256"] != original["entries"][0]["sha256"]
    assert changed["tree_sha256"] != original["tree_sha256"]
    assert restored == original


def test_unknown_ordinary_file_is_included(tmp_path: Path) -> None:
    write_file(tmp_path, "future.unknown", b"future")

    assert build_integrity_manifest(tmp_path)["entries"][0]["path"] == "future.unknown"


def test_empty_directory_does_not_affect_identity(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json")
    before = build_integrity_manifest(tmp_path)
    (tmp_path / "empty/nested").mkdir(parents=True)

    assert build_integrity_manifest(tmp_path) == before


def test_integrity_manifest_excludes_only_its_root_self(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json")
    write_integrity_manifest(tmp_path)

    paths = [entry["path"] for entry in build_integrity_manifest(tmp_path)["entries"]]
    assert INTEGRITY_MANIFEST_FILENAME not in paths
    assert paths == ["result.json"]


def test_nested_file_with_manifest_name_is_an_ordinary_artifact(tmp_path: Path) -> None:
    write_file(tmp_path, f"nested/{INTEGRITY_MANIFEST_FILENAME}")

    assert build_integrity_manifest(tmp_path)["entries"][0]["path"] == (
        f"nested/{INTEGRITY_MANIFEST_FILENAME}"
    )


def test_existing_non_eai_inventory_is_included(tmp_path: Path) -> None:
    write_file(tmp_path, "artifact-hashes.json", b"{}\n")

    assert build_integrity_manifest(tmp_path)["entries"][0]["path"] == (
        "artifact-hashes.json"
    )


@pytest.mark.parametrize("name", OS_METADATA_EXCLUDED)
def test_exact_documented_os_metadata_files_are_excluded(
    tmp_path: Path,
    name: str,
) -> None:
    write_file(tmp_path, name)
    write_file(tmp_path, f"nested/{name}")

    assert build_integrity_manifest(tmp_path)["entries"] == []


@pytest.mark.parametrize("name", ("thumbs.db", ".DS_Store.keep", "desktop.ini.json"))
def test_os_metadata_exclusion_is_not_broad(tmp_path: Path, name: str) -> None:
    write_file(tmp_path, name)

    assert [entry["path"] for entry in build_integrity_manifest(tmp_path)["entries"]] == [name]


@pytest.mark.parametrize("suffix", FORBIDDEN_TRANSIENT_SUFFIXES)
def test_every_frozen_transient_suffix_fails_generation(
    tmp_path: Path,
    suffix: str,
) -> None:
    write_file(tmp_path, f"result{suffix}")

    with pytest.raises(TransientTreeError):
        build_integrity_manifest(tmp_path)


def test_transient_suffix_detection_is_ascii_case_insensitive(tmp_path: Path) -> None:
    write_file(tmp_path, "RESULT.TMP")

    with pytest.raises(TransientTreeError):
        build_integrity_manifest(tmp_path)


def test_successful_generation_leaves_no_temporary_output(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json")
    write_integrity_manifest(tmp_path)

    assert not integrity._temporary_manifest_path(tmp_path.resolve()).exists()


def test_atomic_write_failure_cleans_temporary_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_file(tmp_path, "result.json")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ManifestWriteError):
        write_integrity_manifest(tmp_path)

    assert not integrity._temporary_manifest_path(tmp_path.resolve()).exists()
    assert not manifest_path(tmp_path).exists()


def test_symlink_inside_result_root_fails_safely(tmp_path: Path) -> None:
    target = write_file(tmp_path, "target.json")
    create_symlink_or_skip(tmp_path / "link.json", target)

    with pytest.raises(UnsupportedLinkError):
        build_integrity_manifest(tmp_path)


def test_symlink_cannot_escape_result_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = write_file(tmp_path, "outside.json", b"secret")
    create_symlink_or_skip(root / "escape.json", outside)

    with pytest.raises(UnsupportedLinkError):
        build_integrity_manifest(root)


def test_symlink_result_root_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "root-link"
    create_symlink_or_skip(link, target, directory=True)

    with pytest.raises(UnsupportedLinkError):
        build_integrity_manifest(link)


def test_canonical_json_is_utf8_compact_sorted_and_has_exactly_one_lf(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "\u03b2.json", "snowman \u2603".encode("utf-8"))
    write_integrity_manifest(tmp_path)
    raw = manifest_path(tmp_path).read_bytes()

    assert raw.decode("utf-8")
    assert b'": "' not in raw
    assert b", " not in raw
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert "\u03b2.json".encode("utf-8") in raw
    assert b"\\u03b2" not in raw


def test_canonical_tree_material_has_no_dynamic_or_machine_fields(tmp_path: Path) -> None:
    manifest = build_integrity_manifest(tmp_path)
    serialized = canonical_json_bytes(manifest).decode("utf-8")

    for forbidden in (
        "generated_at",
        "hostname",
        "machine_name",
        "current_git_branch",
        "mtime",
        "ctime",
        "inode",
        "permissions",
        "owner",
    ):
        assert forbidden not in serialized


def test_repeated_generation_is_byte_identical(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json", b"stable")
    first = write_integrity_manifest(tmp_path)
    first_bytes = manifest_path(tmp_path).read_bytes()
    second = write_integrity_manifest(tmp_path)

    assert second == first
    assert manifest_path(tmp_path).read_bytes() == first_bytes


def test_valid_manifest_verifies_repeatedly_without_mutation(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json")
    write_integrity_manifest(tmp_path)
    before = manifest_path(tmp_path).read_bytes()

    assert verify_integrity_manifest(tmp_path).verified
    assert verify_integrity_manifest(tmp_path).verified
    assert manifest_path(tmp_path).read_bytes() == before


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(MissingManifestError):
        verify_integrity_manifest(tmp_path)


def test_unknown_contract_version_fails_closed(tmp_path: Path) -> None:
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["contract"] = "evaluation-artifact-integrity-v2"
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(UnsupportedVersionError):
        verify_integrity_manifest(tmp_path)


@pytest.mark.parametrize("content", (b"{", b"[]\n", b"\xff"))
def test_malformed_manifest_fails_closed(tmp_path: Path, content: bytes) -> None:
    manifest_path(tmp_path).write_bytes(content)

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_missing_scoped_file_fails_verification(tmp_path: Path) -> None:
    path = write_file(tmp_path, "result.json")
    write_integrity_manifest(tmp_path)
    path.unlink()

    with pytest.raises(FileSetMismatchError) as raised:
        verify_integrity_manifest(tmp_path)
    assert raised.value.missing_paths == ("result.json",)


def test_unexpected_scoped_file_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.json")
    write_integrity_manifest(tmp_path)
    write_file(tmp_path, "extra.bin")

    with pytest.raises(FileSetMismatchError) as raised:
        verify_integrity_manifest(tmp_path)
    assert raised.value.unexpected_paths == ("extra.bin",)


def test_modified_same_size_content_fails_verification(tmp_path: Path) -> None:
    path = write_file(tmp_path, "result.bin", b"abc")
    write_integrity_manifest(tmp_path)
    path.write_bytes(b"abd")

    with pytest.raises(ContentMismatchError, match="SHA-256 mismatch"):
        verify_integrity_manifest(tmp_path)


def test_modified_size_fails_verification(tmp_path: Path) -> None:
    path = write_file(tmp_path, "result.bin", b"abc")
    write_integrity_manifest(tmp_path)
    path.write_bytes(b"abcd")

    with pytest.raises(ContentMismatchError, match="size mismatch"):
        verify_integrity_manifest(tmp_path)


def test_tampered_entry_hash_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin", b"abc")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"][0]["sha256"] = "0" * 64
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(ContentMismatchError):
        verify_integrity_manifest(tmp_path)


def test_tampered_entry_size_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin", b"abc")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"][0]["size_bytes"] += 1
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(ContentMismatchError):
        verify_integrity_manifest(tmp_path)


def test_tampered_tree_hash_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["tree_sha256"] = "0" * 64
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(TreeDigestMismatchError):
        verify_integrity_manifest(tmp_path)


def test_tampered_scope_metadata_fails_verification(tmp_path: Path) -> None:
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["scope"]["root"] = "elsewhere"
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_duplicate_manifest_path_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"].append(dict(manifest["entries"][0]))
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(CanonicalPathCollisionError):
        verify_integrity_manifest(tmp_path)


def test_manifest_traversal_rejected_before_tree_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_file(tmp_path, "result.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"][0]["path"] = "../outside.bin"
    rewrite_manifest(tmp_path, manifest)
    monkeypatch.setattr(
        integrity,
        "_collect_entries",
        lambda _: pytest.fail("tree scan occurred before manifest-path validation"),
    )

    with pytest.raises(CanonicalPathError):
        verify_integrity_manifest(tmp_path)


def test_drive_qualified_manifest_path_fails_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"][0]["path"] = r"C:\outside.bin"
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(CanonicalPathError):
        verify_integrity_manifest(tmp_path)


def test_noncanonical_manifest_whitespace_fails_verification(tmp_path: Path) -> None:
    write_integrity_manifest(tmp_path)
    manifest_path(tmp_path).write_text(
        json.dumps(load_manifest(tmp_path), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_uppercase_digest_is_not_canonical_machine_output(tmp_path: Path) -> None:
    write_file(tmp_path, "result.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"][0]["sha256"] = manifest["entries"][0]["sha256"].upper()
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_unknown_manifest_field_fails_verification(tmp_path: Path) -> None:
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["generated_at"] = "never canonical"
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_out_of_order_manifest_entries_fail_verification(tmp_path: Path) -> None:
    write_file(tmp_path, "a.bin")
    write_file(tmp_path, "b.bin")
    write_integrity_manifest(tmp_path)
    manifest = load_manifest(tmp_path)
    manifest["entries"].reverse()
    rewrite_manifest(tmp_path, manifest)

    with pytest.raises(MalformedManifestError):
        verify_integrity_manifest(tmp_path)


def test_absolute_parent_directory_does_not_affect_identity(tmp_path: Path) -> None:
    first = tmp_path / "parent-one/result"
    second = tmp_path / "different-parent/result"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    write_file(first, "nested/result.json", b"same")
    write_file(second, "nested/result.json", b"same")

    assert build_integrity_manifest(first) == build_integrity_manifest(second)


def test_invalid_missing_root_is_structured() -> None:
    with pytest.raises(InvalidRootError):
        build_integrity_manifest(Path("definitely-missing-eai-root"))


def test_regular_file_cannot_be_used_as_result_root(tmp_path: Path) -> None:
    root = write_file(tmp_path, "not-a-directory")

    with pytest.raises(InvalidRootError):
        build_integrity_manifest(root)


def test_cli_generate_and_verify_succeed_without_absolute_path_leak(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_file(tmp_path, "result.json")

    assert main(["generate", "--root", str(tmp_path)]) == 0
    generated = capsys.readouterr()
    assert "verification=generated" in generated.out
    assert str(tmp_path.resolve()) not in generated.out

    assert main(["verify", "--root", str(tmp_path)]) == 0
    verified = capsys.readouterr()
    assert "verification=valid" in verified.out
    assert "included_files=1" in verified.out
    assert str(tmp_path.resolve()) not in verified.out


def test_cli_verification_mismatch_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_file(tmp_path, "result.json", b"before")
    write_integrity_manifest(tmp_path)
    path.write_bytes(b"after")

    assert main(["verify", "--root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "verification=failed" in captured.err
    assert "error_code=content_mismatch" in captured.err


def test_cli_missing_manifest_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["verify", "--root", str(tmp_path)]) == 2

    captured = capsys.readouterr()
    assert "error_code=missing_manifest" in captured.err


def test_generic_implementation_contains_no_scenario_specific_identity() -> None:
    source = Path(integrity.__file__).read_text(encoding="utf-8")
    forbidden = (
        "NONCAUSAL_CONTROL",
        "lineage-2a",
        "count-50",
        "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe",
        "a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed",
        "32695735269",
    )

    assert all(value not in source for value in forbidden)


def test_implementation_has_no_historical_result_root_or_backfill_target() -> None:
    source = Path(integrity.__file__).read_text(encoding="utf-8")

    assert "evaluation/results" not in source
    assert "post-sc4" not in source
    assert "artifact-hashes.json" not in source


def test_tests_use_only_pytest_temporary_roots_for_generation() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    historical_result_prefix = "evaluation" + "/results/lineage"

    assert "write_integrity_manifest(tmp_path" in source
    assert historical_result_prefix not in source
