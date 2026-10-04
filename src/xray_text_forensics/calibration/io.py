"""JSONL interchange for benchmark scores."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import ScoreSample


def load_score_jsonl(path: Path) -> list[ScoreSample]:
    samples: list[ScoreSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                samples.append(ScoreSample.model_validate(payload))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid score record") from exc
    return samples
