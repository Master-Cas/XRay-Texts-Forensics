import subprocess
from pathlib import Path

from scripts import dependency_audit


def test_venv_python_is_cross_platform() -> None:
    root = Path("audit-env")
    assert dependency_audit.venv_python(root, "posix") == root / "bin" / "python"
    assert dependency_audit.venv_python(root, "nt") == root / "Scripts" / "python.exe"


def test_audit_command_is_strict_without_suppressions() -> None:
    command = dependency_audit.audit_command(
        Path("auditor-python"),
        Path("target-site-packages"),
    )

    assert command[:3] == ["auditor-python", "-m", "pip_audit"]
    assert "--strict" in command
    assert command[command.index("--progress-spinner") + 1] == "off"
    assert command[command.index("--aliases") + 1] == "on"
    assert command[command.index("--desc") + 1] == "off"
    assert command[command.index("--path") + 1] == "target-site-packages"
    assert "--ignore-vuln" not in command


def test_run_audit_preserves_nonzero_exit_code(monkeypatch) -> None:
    expected = 23

    def fake_run(args, *, check):  # noqa: ANN001
        assert "--strict" in args
        assert check is False
        return subprocess.CompletedProcess(args, expected)

    monkeypatch.setattr(dependency_audit.subprocess, "run", fake_run)

    assert (
        dependency_audit.run_audit(
            Path("auditor-python"),
            Path("target-site-packages"),
        )
        == expected
    )


def test_workflow_keeps_two_os_fail_closed_gate() -> None:
    workflow = Path(".github/workflows/dependency-audit.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Dependency audit" in workflow
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert 'python-version: "3.12.6"' in workflow
    assert "python scripts/dependency_audit.py" in workflow
    assert "contents: read" in workflow
