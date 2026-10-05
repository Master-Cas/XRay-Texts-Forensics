from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

AUDITOR_VERSION = "2.10.1"
TARGET_PIP_VERSION = "26.2.1"
TARGET_EXTRAS = ".[dev,desktop,packaging]"
LOCAL_DISTRIBUTION = "xray-texts-forensics"


def venv_python(venv_dir: Path, os_name: str | None = None) -> Path:
    platform = os.name if os_name is None else os_name
    if platform == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run_checked(args: Sequence[str], *, cwd: Path | None = None) -> None:
    command = [str(arg) for arg in args]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def capture(args: Sequence[str], *, cwd: Path | None = None) -> str:
    command = [str(arg) for arg in args]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def audit_command(auditor_python: Path, site_packages: Path) -> list[str]:
    return [
        str(auditor_python),
        "-m",
        "pip_audit",
        "--strict",
        "--progress-spinner",
        "off",
        "--aliases",
        "on",
        "--desc",
        "off",
        "--path",
        str(site_packages),
    ]


def run_audit(auditor_python: Path, site_packages: Path) -> int:
    command = audit_command(auditor_python, site_packages)
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def installed_distribution_count(target_python: Path) -> int:
    raw = capture([str(target_python), "-m", "pip", "list", "--format", "json"])
    packages = json.loads(raw)
    if not isinstance(packages, list):
        raise RuntimeError("pip list returned an unexpected payload")
    return len(packages)


def site_packages_path(target_python: Path) -> Path:
    raw = capture(
        [
            str(target_python),
            "-c",
            "import site; print(site.getsitepackages()[0])",
        ]
    )
    path = Path(raw)
    if not path.exists():
        raise RuntimeError(f"target site-packages does not exist: {path}")
    return path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="xray-dependency-audit-") as temp_dir:
        temp_root = Path(temp_dir)
        target_dir = temp_root / "target"
        auditor_dir = temp_root / "auditor"

        run_checked([sys.executable, "-m", "venv", str(target_dir)])
        target_python = venv_python(target_dir)
        run_checked(
            [
                str(target_python),
                "-m",
                "pip",
                "install",
                f"pip=={TARGET_PIP_VERSION}",
            ]
        )
        run_checked(
            [str(target_python), "-m", "pip", "install", TARGET_EXTRAS],
            cwd=repo_root,
        )
        run_checked(
            [
                str(target_python),
                "-m",
                "pip",
                "uninstall",
                "-y",
                LOCAL_DISTRIBUTION,
            ],
            cwd=repo_root,
        )
        run_checked([str(target_python), "-m", "pip", "check"])

        run_checked([sys.executable, "-m", "venv", str(auditor_dir)])
        auditor_python = venv_python(auditor_dir)
        run_checked(
            [
                str(auditor_python),
                "-m",
                "pip",
                "install",
                f"pip-audit=={AUDITOR_VERSION}",
            ]
        )

        package_count = installed_distribution_count(target_python)
        site_packages = site_packages_path(target_python)
        print(f"AUDIT_TARGET_PACKAGE_COUNT={package_count}", flush=True)
        print(f"AUDIT_TARGET_SITE_PACKAGES={site_packages}", flush=True)
        print(f"TARGET_PIP_VERSION={TARGET_PIP_VERSION}", flush=True)
        print(f"PIP_AUDIT_VERSION={AUDITOR_VERSION}", flush=True)

        return run_audit(auditor_python, site_packages)


if __name__ == "__main__":
    raise SystemExit(main())
