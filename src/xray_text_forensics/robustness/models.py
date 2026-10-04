"""Typed robustness-lab results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PreservationMetrics(BaseModel):
    original_token_count: int
    transformed_token_count: int
    token_jaccard: float = Field(ge=0.0, le=1.0)
    token_sequence_ratio: float = Field(ge=0.0, le=1.0)
    fivegram_survival: float = Field(ge=0.0, le=1.0)
    lexical_tfidf_cosine: float = Field(ge=0.0, le=1.0)
    char_length_ratio: float = Field(ge=0.0)


class WatermarkMeasurement(BaseModel):
    status: str
    scored_tokens: int
    green_tokens: int
    green_fraction: float
    z_score: float
    one_sided_p_value: float
    threshold_z: float
    min_scored_tokens: int


class StressResult(BaseModel):
    transform_id: str
    transform_description: str
    transformed_sha256: str
    preservation: PreservationMetrics
    measurement: WatermarkMeasurement
    z_delta_from_baseline: float
    detection_retained: bool | None


class RobustnessReport(BaseModel):
    original_sha256: str
    scheme: str = "xray-reference-redgreen-v1"
    baseline: WatermarkMeasurement
    results: list[StressResult]
    scientific_note: str = (
        "Preservation metrics are lexical/sequence metrics, not semantic-equivalence "
        "proof. Robustness results for the XRay reference scheme must not be "
        "extrapolated directly to a secret production watermark."
    )
