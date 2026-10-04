"""Interchange helpers for externally collected black-box experiments."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .models import BlackBoxDesign, CellObservation


def save_design(path: Path, design: BlackBoxDesign) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(design.model_dump_json(indent=2), encoding="utf-8")


def load_design(path: Path) -> BlackBoxDesign:
    try:
        return BlackBoxDesign.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid black-box design") from exc


def save_observations_jsonl(
    path: Path,
    observations: list[CellObservation],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(observation.model_dump_json() + "\n" for observation in observations),
        encoding="utf-8",
    )


def load_observations_jsonl(path: Path) -> list[CellObservation]:
    observations: list[CellObservation] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                observations.append(CellObservation.model_validate_json(line))
            except ValidationError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid black-box observation"
                ) from exc
    return observations
