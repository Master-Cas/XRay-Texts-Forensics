from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
PINNED_REMOTE_RE = re.compile(r"^[^@\s]+@[0-9a-fA-F]{40}$")


def remote_action_pin_violations(text: str) -> list[str]:
    violations: list[str] = []
    for reference in USES_RE.findall(text):
        if reference.startswith("./"):
            continue
        if not PINNED_REMOTE_RE.fullmatch(reference):
            violations.append(reference)
    return violations


def workflow_files() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOW_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


def test_all_remote_workflow_actions_are_pinned_to_full_commit_shas() -> None:
    files = workflow_files()
    assert files, "expected at least one GitHub Actions workflow"

    violations: dict[str, list[str]] = {}
    for path in files:
        refs = remote_action_pin_violations(path.read_text(encoding="utf-8"))
        if refs:
            violations[str(path)] = refs

    assert not violations, f"floating GitHub Action references found: {violations}"


def test_local_actions_are_allowed() -> None:
    assert remote_action_pin_violations("steps:\n  - uses: ./actions/local\n") == []


def test_floating_remote_action_reference_is_rejected() -> None:
    assert remote_action_pin_violations("steps:\n  - uses: actions/checkout@v4\n") == [
        "actions/checkout@v4"
    ]


def test_tagged_remote_action_reference_is_rejected() -> None:
    assert remote_action_pin_violations(
        "steps:\n  - uses: owner/action@release-tag\n"
    ) == ["owner/action@release-tag"]


def test_full_sha_remote_action_reference_is_allowed() -> None:
    assert (
        remote_action_pin_violations(
            "steps:\n"
            "  - uses: owner/action@0123456789abcdef0123456789abcdef01234567\n"
        )
        == []
    )
