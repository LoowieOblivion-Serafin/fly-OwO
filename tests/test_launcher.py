"""Startup must explain missing tools before downloading large model data."""
import pytest
import subprocess

import run_flysonic as launcher
from flysonic import srb2


def test_missing_toolchain_stops_before_venv(monkeypatch):
    def missing():
        raise srb2.SetupError("missing test toolchain")

    def unexpected_setup():
        pytest.fail("dependency installation ran before toolchain validation")

    monkeypatch.setattr(srb2, "build_environment", missing)
    monkeypatch.setattr(launcher, "ensure_venv", unexpected_setup)
    with pytest.raises(SystemExit, match="missing test toolchain"):
        launcher.main([])


def test_help_does_not_install_dependencies(monkeypatch, capsys):
    def unexpected_setup():
        pytest.fail("--help must not install dependencies")

    monkeypatch.setattr(launcher, "ensure_venv", unexpected_setup)
    with pytest.raises(SystemExit) as result:
        launcher.main(["--help"])
    assert result.value.code == 0
    assert "--demo-model" in capsys.readouterr().out


@pytest.mark.parametrize("returncode", [3236495362, -1058471934])
def test_code_integrity_block_has_actionable_message(monkeypatch, returncode):
    def blocked(command, **kwargs):
        raise subprocess.CalledProcessError(returncode, command)

    monkeypatch.setattr(srb2.subprocess, "run", blocked)
    with pytest.raises(srb2.SetupError, match="0xC0E90002") as result:
        srb2.run(["cmake", "--version"])
    assert "CodeIntegrity" in str(result.value)


def test_other_command_failures_keep_original_error(monkeypatch):
    original = subprocess.CalledProcessError(1, ["cmake", "--build", "."])

    def failed(command, **kwargs):
        raise original

    monkeypatch.setattr(srb2.subprocess, "run", failed)
    with pytest.raises(subprocess.CalledProcessError) as result:
        srb2.run(original.cmd)
    assert result.value is original
