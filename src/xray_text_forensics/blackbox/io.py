"""JSONL interchange for black-box observations."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .models import BlackBoxObservation


def load_observations_jsonl(path: Path) -> list[BlackBoxObservation]:
    rows: list[BlackBoxObservation] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(BlackBoxObservation.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(f"{path}:{line_number}: invalid observation") from exc
    return rows


def save_observations_jsonl(
    path: Path,
    observations: list[BlackBoxObservation],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in observations),
        encoding="utf-8",
    )
