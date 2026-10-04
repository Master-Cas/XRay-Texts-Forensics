from __future__ import annotations

from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_authenticode_helper_uses_sha256_timestamp_and_verification() -> None:
    script = (
        repository_root() / "packaging" / "windows" / "sign-authenticode.ps1"
    ).read_text(encoding="utf-8")

    assert "/fd SHA256" in script
    assert "/tr $TimestampUrl" in script
    assert "/td SHA256" in script
    assert "verify /pa /all /v" in script
    assert "Get-AuthenticodeSignature" in script
    assert 'Status -ne "Valid"' in script
    assert "ProbeOnly" in script


def test_windows_workflow_supports_all_or_none_signing_secrets() -> None:
    workflow = (
        repository_root() / ".github" / "workflows" / "windows-desktop.yml"
    ).read_text(encoding="utf-8")

    assert "XRAY_SIGNING_PFX_B64" in workflow
    assert "XRAY_SIGNING_PFX_PASSWORD" in workflow
    assert "XRAY_SIGNING_TIMESTAMP_URL" in workflow
    assert "partially configured; expected all three or none" in workflow
    assert "sign-authenticode.ps1 -ProbeOnly" in workflow


def test_windows_workflow_signs_both_binary_layers_when_enabled() -> None:
    workflow = (
        repository_root() / ".github" / "workflows" / "windows-desktop.yml"
    ).read_text(encoding="utf-8")

    assert 'Sign portable executable' in workflow
    assert '-FilePath "dist/XRay-Texts-Forensics/XRay-Texts-Forensics.exe"' in workflow
    assert 'Sign installer' in workflow
    assert (
        '-FilePath "dist-installer/XRay-Texts-Forensics-Windows-Setup.exe"'
        in workflow
    )


def test_artifacts_expose_explicit_signing_status() -> None:
    workflow = (
        repository_root() / ".github" / "workflows" / "windows-desktop.yml"
    ).read_text(encoding="utf-8")

    assert workflow.count("SIGNED_AUTHENTICODE") >= 2
    assert workflow.count("UNSIGNED_ALPHA") >= 2
    assert "dist/XRay-Texts-Forensics/SIGNING-STATUS.txt" in workflow
    assert "dist-installer/SIGNING-STATUS.txt" in workflow


def test_signing_material_is_only_referenced_as_ci_secrets() -> None:
    root = repository_root()
    workflow = (
        root / ".github" / "workflows" / "windows-desktop.yml"
    ).read_text(encoding="utf-8")
    script = (
        root / "packaging" / "windows" / "sign-authenticode.ps1"
    ).read_text(encoding="utf-8")

    assert "secrets.XRAY_SIGNING_PFX_B64" in workflow
    assert "secrets.XRAY_SIGNING_PFX_PASSWORD" in workflow
    assert "secrets.XRAY_SIGNING_TIMESTAMP_URL" in workflow
    assert "BEGIN CERTIFICATE" not in workflow
    assert "BEGIN CERTIFICATE" not in script
    assert "BEGIN PRIVATE KEY" not in workflow
    assert "BEGIN PRIVATE KEY" not in script
