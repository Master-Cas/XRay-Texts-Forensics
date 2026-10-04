"""Typed records for black-box forced-choice experiments."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PromptCell(BaseModel):
    experiment_id: str
    prefix_id: str
    context_id: str
    prefix: str
    context: str
    choices: list[str] = Field(min_length=2)


class BlackBoxDesign(BaseModel):
    experiment_id: str
    prefixes: dict[str, str]
    contexts: dict[str, str]
    choices: list[str] = Field(min_length=2)
    repeats: int = Field(ge=1)
    seed: int
    cells: list[PromptCell]

    @model_validator(mode="after")
    def unique_design(self) -> BlackBoxDesign:
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("choices must be unique")
        if len(set(self.contexts.values())) != len(self.contexts):
            raise ValueError("contexts must be unique")
        expected = len(self.prefixes) * len(self.contexts)
        if len(self.cells) != expected:
            raise ValueError("cells must contain every prefix/context combination")
        return self


class BlackBoxObservation(BaseModel):
    experiment_id: str
    prefix_id: str
    context_id: str
    repeat_index: int = Field(ge=0)
    choice: str | None = None
    allowed_choices: list[str] = Field(min_length=2)
    valid: bool
    raw_output: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PrefixStatistic(BaseModel):
    prefix_id: str
    statistic: float
    valid_observations: int
    context_count: int
    choice_count: int


class BlackBoxAnalysisResult(BaseModel):
    experiment_id: str
    valid_observations: int
    invalid_observations: int
    prefix_count: int
    context_count: int
    choice_count: int
    statistic: float
    association_index: float
    p_value: float
    permutations: int
    seed: int
    per_prefix: list[PrefixStatistic]
    interpretation: str = (
        "A small permutation p-value is evidence of repeatable context-dependent "
        "forced-choice bias after controlling for prefix-level choice preferences. "
        "It is compatible with keyed sampling behavior but does not recover a secret "
        "watermark key or prove provider provenance."
    )


class BlackBoxValidationResult(BaseModel):
    off_result: BlackBoxAnalysisResult
    on_result: BlackBoxAnalysisResult
    alpha: float
    passed: bool
    criterion: str
