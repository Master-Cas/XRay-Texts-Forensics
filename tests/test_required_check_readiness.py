from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_DIR = Path(".github/workflows")


def workflow(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def event_block(text: str, event: str) -> list[str]:
    lines = text.splitlines()
    marker = f"  {event}:"
    start = lines.index(marker)
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if indent <= 2:
                break
        block.append(line)
    return block


def test_ci_required_context_name_is_stable() -> None:
    text = workflow("ci.yml")
    assert re.search(
        r"(?m)^  test:\n    name: CI / test\n    runs-on: ubuntu-latest$",
        text,
    )


def test_windows_required_context_name_is_stable() -> None:
    text = workflow("windows-desktop.yml")
    assert re.search(
        r"(?m)^  build:\n    name: Windows Desktop / build\n"
        r"    runs-on: windows-latest$",
        text,
    )


def test_windows_pull_request_trigger_is_unconditional() -> None:
    block = event_block(workflow("windows-desktop.yml"), "pull_request")
    body = "\n".join(block)
    assert "paths:" not in body
    assert "paths-ignore:" not in body
    assert not any(line.strip() for line in block)


def test_windows_push_paths_are_preserved() -> None:
    block = event_block(workflow("windows-desktop.yml"), "push")
    paths = [
        match.group(1)
        for line in block
        if (match := re.match(r'^\s+- "([^"]+)"$', line))
    ]
    assert paths == [
        "src/**",
        "packaging/windows/**",
        "pyproject.toml",
        ".github/workflows/windows-desktop.yml",
    ]


def test_dependency_audit_matrix_context_names_are_stable() -> None:
    text = workflow("dependency-audit.yml")
    assert "    name: Dependency audit (${{ matrix.os }})\n" in text
    assert re.search(
        r"(?ms)^      matrix:\n"
        r"        os:\n"
        r"          - ubuntu-latest\n"
        r"          - windows-latest$",
        text,
    )
