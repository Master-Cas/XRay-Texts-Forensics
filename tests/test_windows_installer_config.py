from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

from xray_text_forensics import __version__
from xray_text_forensics.web import WebSettings, create_app


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_package_version_matches_installed_distribution_and_pyproject() -> None:
    root = repository_root()
    with (root / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    assert __version__ == importlib.metadata.version("xray-texts-forensics")
    assert __version__ == project_version


def test_fastapi_reports_the_same_package_version(tmp_path) -> None:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="test",
            request_logging=False,
        )
    )
    assert app.version == __version__


def test_installer_is_per_user_and_preserves_forensic_data() -> None:
    script = (
        repository_root() / "packaging" / "windows" / "installer.iss"
    ).read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in script
    assert "DefaultDirName={localappdata}\\Programs\\XRay Texts Forensics" in script
    assert "XRay Texts Forensics.exe" in script
    assert "[UninstallDelete]" not in script
    assert "userappdata" not in script.casefold()


def test_windows_workflow_smoke_installs_and_checks_data_retention() -> None:
    workflow = (
        repository_root() / ".github" / "workflows" / "windows-desktop.yml"
    ).read_text(encoding="utf-8")

    assert "Build installer" in workflow
    assert "Smoke install and uninstall" in workflow
    assert "installer-data-retention-marker.txt" in workflow
    assert "User forensic data was deleted by uninstall" in workflow
    assert "XRay-Texts-Forensics-Windows-Installer-alpha" in workflow
