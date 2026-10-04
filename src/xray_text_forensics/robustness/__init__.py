"""Adversarial robustness and transformation-preservation analysis."""

from .lab import compare_texts, run_reference_watermark_stress
from .models import (
    PreservationMetrics,
    RobustnessReport,
    StressResult,
    WatermarkMeasurement,
)
from .transforms import default_stress_transforms

__all__ = [
    "PreservationMetrics",
    "RobustnessReport",
    "StressResult",
    "WatermarkMeasurement",
    "compare_texts",
    "default_stress_transforms",
    "run_reference_watermark_stress",
]
