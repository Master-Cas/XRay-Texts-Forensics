"""Typed calibration and benchmark records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from xray_text_forensics.core.models import utc_now


class ScoreSample(BaseModel):
    sample_id: str
    label: bool
    score: float
    length: int = Field(ge=0)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CalibrationConfig(BaseModel):
    target_fpr: float = Field(default=0.01, gt=0.0, lt=1.0)
    higher_is_positive: bool = True
    min_control_samples: int = Field(default=100, ge=1)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)


class CalibrationManifest(BaseModel):
    calibration_id: str
    detector_id: str
    detector_version: str
    dataset_id: str
    dataset_version: str
    target_fpr: float
    higher_is_positive: bool
    threshold: float
    dev_control_count: int
    dev_false_positives: int
    dev_empirical_fpr: float
    controls_sha256: str
    created_at: datetime = Field(default_factory=utc_now)


class RateInterval(BaseModel):
    rate: float
    lower: float
    upper: float
    numerator: int
    denominator: int


class LengthBucketMetrics(BaseModel):
    label: str
    minimum: int
    maximum: int | None
    sample_count: int
    positive_count: int
    negative_count: int
    tpr: float | None = None
    fpr: float | None = None


class EvaluationReport(BaseModel):
    manifest: CalibrationManifest
    sample_count: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    tpr: float
    fpr: float
    precision: float
    recall: float
    roc_auc: float | None
    tpr_interval: RateInterval
    fpr_interval: RateInterval
    length_buckets: list[LengthBucketMetrics]

    @model_validator(mode="after")
    def confusion_total_matches(self) -> EvaluationReport:
        total = self.true_positive + self.false_positive + self.true_negative + self.false_negative
        if total != self.sample_count:
            raise ValueError("confusion-matrix counts must equal sample_count")
        return self
