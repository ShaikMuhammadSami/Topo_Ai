"""PH-4E hostile agent-local credential custody acceptance."""

from __future__ import annotations

import os
import stat

import pytest

from topo_agent import config
from topo_agent.main import app
from typer.testing import CliRunner


def _marker() -> str:
    import secrets

    return f"AGENT_TOKEN_{secrets.token_hex(18)}"


def test_agent_has_no_raw_argv_path_and_preflights_before_material(monkeypatch, tmp_path):
    monkeypatch.setenv("TOPO_AGENT_HOME", str(tmp_path))
    help_result = CliRunner().invoke(app, ["enroll", "--help"])
    assert help_result.exit_code == 0
    assert "--token-stdin" in help_result.output
    assert "--token " not in help_result.output
    config.preflight_agent_token_storage()
    assert not list(tmp_path.glob("*.preflight"))


def test_agent_atomic_write_is_restrictive_and_failure_leaves_no_raw_fallback(
    monkeypatch, tmp_path, capsys
):
    marker = _marker()
    monkeypatch.setenv("TOPO_AGENT_HOME", str(tmp_path))
    observed_modes = []
    real_fstat = config.os.fstat

    def observed_fstat(descriptor):
        result = real_fstat(descriptor)
        observed_modes.append(stat.S_IMODE(result.st_mode))
        return result

    monkeypatch.setattr(config.os, "fstat", observed_fstat)
    path = config.store_agent_token(marker)
    assert config.load_agent_token() == marker
    if os.name == "posix":
        assert observed_modes and observed_modes[0] == 0o600
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        descriptor = config._windows_security_descriptor(path)
        assert descriptor.startswith("D:P")
        assert not any(principal in descriptor for principal in (";;;WD)", ";;;BU)", ";;;AU)"))
    captured = capsys.readouterr()
    assert marker not in captured.out and marker not in captured.err

    real_write = config.os.write
    monkeypatch.setattr(
        config.os,
        "write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic write failure")),
    )
    replacement = _marker()
    with pytest.raises(OSError, match="write failure"):
        config.store_agent_token(replacement)
    monkeypatch.setattr(config.os, "write", real_write)
    assert config.load_agent_token() == marker
    assert replacement not in capsys.readouterr().out
    assert not list(tmp_path.glob("*.tmp"))

