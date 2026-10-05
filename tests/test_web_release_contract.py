from __future__ import annotations

import re
import subprocess
from pathlib import Path

SCRIPT = Path("scripts/deploy_xtf_web.sh")
DOCS = Path("docs/operations/XTF_WEB_DEPLOYMENT.md")


def test_deploy_script_rejects_non_sha_before_remote_work() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "not-a-sha"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "40 lowercase hex" in result.stderr


def test_deploy_script_has_release_safety_invariants() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert '[[ "$1" =~ ^[0-9a-f]{40}$ ]]' in text
    assert "git ls-remote origin refs/heads/main" in text
    assert '[[ "$sha" == "$origin_main" ]]' in text
    assert "flock -n" in text
    assert "/opt/xtf/releases/$sha" in text
    assert 'image="xtf:$sha"' in text
    assert "docker build --pull" in text
    assert 'docker run --rm -e "XRAY_BUILD_SHA=$sha"' in text
    assert "tar --numeric-owner -C /var/lib" in text
    assert "docker compose" in text
    assert "up -d --no-deps" in text
    assert "/api/v1/health" in text
    assert "/api/v1/ready" in text
    assert 'payload.get("build_sha") == expected_sha' in text
    assert "rollback()" in text


def test_deploy_script_preserves_data_secrets_and_caddy() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'data_root="/var/lib/xtf"' in text
    assert 'reference_root="$xtf_root/reference-data/library"' in text
    assert 'env_file="$deploy_dir/xtf.env"' in text
    assert '[[ -e "$path" ]]' in text
    assert "docker compose down" not in text
    assert "docker volume" not in text
    assert "docker system prune" not in text
    assert "rm -rf" not in text
    assert 'cat "$env_file"' not in text
    assert '> "$env_file"' not in text
    assert "Caddyfile" not in text
    assert not re.search(r"docker\s+(restart|stop).*caddy", text, re.IGNORECASE)


def test_dry_run_exits_before_ssh() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    dry_run_gate = text.index("if (( dry_run )); then")
    ssh_call = text.index("\nssh -o BatchMode=yes")
    gate_body = text[dry_run_gate:ssh_call]

    assert "dry_run_plan" in gate_body
    assert "exit 0" in gate_body
    assert "ssh " not in gate_body


def test_release_contract_documents_real_production_topology() -> None:
    text = DOCS.read_text(encoding="utf-8")

    for required in (
        "https://xtf.technolution.cl",
        "51.161.113.154",
        "/opt/xtf/current",
        "/opt/xtf/releases/<SHA>",
        "/opt/xtf/deploy/compose.yaml",
        "/opt/xtf/deploy/xtf.env",
        "/var/lib/xtf",
        "/opt/xtf/reference-data/library",
        "read-only",
        "Automatic rollback",
        "Secrets policy",
    ):
        assert required in text
