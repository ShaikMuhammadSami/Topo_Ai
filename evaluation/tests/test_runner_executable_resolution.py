from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import runner


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test executable", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_windows_virtual_environment_paths_are_explicit() -> None:
    assert runner._venv_executable_candidates(
        "backend", "python", os_name="nt"
    ) == (
        runner.REPOSITORY_ROOT / "backend/.venv/Scripts/python.exe",
    )
    assert runner._venv_executable_candidates(
        "agent", "topo-agent", os_name="nt"
    ) == (
        runner.REPOSITORY_ROOT / "agent/.venv/Scripts/topo-agent.exe",
    )


def test_posix_virtual_environment_paths_are_explicit() -> None:
    assert runner._venv_executable_candidates(
        "backend", "python", os_name="posix"
    ) == (
        runner.REPOSITORY_ROOT / "backend/.venv/bin/python",
    )
    assert runner._venv_executable_candidates(
        "agent", "topo-agent", os_name="posix"
    ) == (
        runner.REPOSITORY_ROOT / "agent/.venv/bin/topo-agent",
    )


def test_explicit_absolute_executable_wins(tmp_path: Path, monkeypatch) -> None:
    configured = _executable(tmp_path / "configured-python")
    monkeypatch.setenv("TOPO_TEST_EXECUTABLE", str(configured))

    resolved = runner._resolve_executable(
        purpose="Test",
        environment_variable="TOPO_TEST_EXECUTABLE",
        candidates=(tmp_path / "missing-default",),
    )

    assert resolved == configured.resolve()


def test_relative_override_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("TOPO_TEST_EXECUTABLE", "relative/python")

    with pytest.raises(RuntimeError, match="must be an absolute path"):
        runner._resolve_executable(
            purpose="Test",
            environment_variable="TOPO_TEST_EXECUTABLE",
            candidates=(),
        )


def test_missing_executable_reports_checked_paths_and_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    missing = tmp_path / "missing-python"
    monkeypatch.delenv("TOPO_TEST_EXECUTABLE", raising=False)

    with pytest.raises(RuntimeError) as raised:
        runner._resolve_executable(
            purpose="Test Python",
            environment_variable="TOPO_TEST_EXECUTABLE",
            candidates=(missing,),
        )

    message = str(raised.value)
    assert "Test Python executable was not found or is not executable" in message
    assert str(missing) in message
    assert "TOPO_TEST_EXECUTABLE" in message


def test_resolution_never_searches_global_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TOPO_TEST_EXECUTABLE", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "unrelated-global-bin"))

    with pytest.raises(RuntimeError, match="Create the repository-local"):
        runner._resolve_executable(
            purpose="Test",
            environment_variable="TOPO_TEST_EXECUTABLE",
            candidates=(tmp_path / "repository-venv-python",),
        )
