"""Black-box forced-choice watermark experiments."""

from .analyze import analyze_observations
from .design import build_design, default_validation_design
from .endpoint import SyntheticChoiceEndpoint, collect_observations
from .models import (
    BlackBoxAnalysisResult,
    BlackBoxDesign,
    BlackBoxObservation,
    BlackBoxValidationResult,
    PromptCell,
)
from .validation import run_synthetic_validation

__all__ = [
    "BlackBoxAnalysisResult",
    "BlackBoxDesign",
    "BlackBoxObservation",
    "BlackBoxValidationResult",
    "PromptCell",
    "SyntheticChoiceEndpoint",
    "analyze_observations",
    "build_design",
    "collect_observations",
    "default_validation_design",
    "run_synthetic_validation",
]
