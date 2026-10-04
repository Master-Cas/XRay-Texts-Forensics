"""Typed black-box experiment models."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field, model_validator


class BlackBoxDesign(BaseModel):
    """Frozen experimental design for a forced-choice black-box audit."""

    prefixes: list[str]
    contexts: list[str]
    candidates: list[str]
    samples_per_cell: int = Field(default=40, ge=2)
    permutation_count: int = Field(default=499, ge=19)
    alpha: float = Field(default=0.01, gt=0.0, lt=1.0)
    seed: int = 20261004

    @model_validator(mode="after")
    def validate_design(self) -> BlackBoxDesign:
        if len(self.prefixes) < 3:
            raise ValueError("At least three prefixes are required")
        if len(self.contexts) < 4:
            raise ValueError("At least four contexts are required")
        if len(self.candidates) < 2:
            raise ValueError("At least two candidates are required")
        for name, values in (
            ("prefixes", self.prefixes),
            ("contexts", self.contexts),
            ("candidates", self.candidates),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be unique")
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain blank values")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class CellObservation(BaseModel):
    prefix_index: int = Field(ge=0)
    context_index: int = Field(ge=0)
    sample_index: int = Field(ge=0)
    choice_index: int = Field(ge=0)
    design_sha256: str | None = None
    raw_output: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class BlackBoxResult(BaseModel):
    provider_id: str
    model_id: str
    design_sha256: str
    observation_count: int
    statistic: float
    p_value: float
    significant: bool
    alpha: float
    permutation_count: int
    method: str = "within-prefix context-alignment permutation test v1"
    interpretation: str = (
        "A significant result is evidence of repeatable context-conditioned choice bias "
        "under this experimental design. It does not by itself identify a watermark "
        "scheme, recover a secret key, or establish provider provenance."
    )
    context_candidate_residuals: list[list[float]] = Field(default_factory=list)


class BlackBoxSelfTestReport(BaseModel):
    design_sha256: str
    off: BlackBoxResult
    on: BlackBoxResult
    validated: bool
    validation_rule: str = (
        "OFF must be non-significant and ON must be significant under the same design."
    )
