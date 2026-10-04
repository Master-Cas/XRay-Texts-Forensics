"""Black-box statistical audit framework."""

from .experiment import BlackBoxExperiment, blackbox_selftest
from .models import (
    BlackBoxDesign,
    BlackBoxResult,
    BlackBoxSelfTestReport,
    CellObservation,
)
from .providers import ChoiceProvider, SyntheticChoiceProvider

__all__ = [
    "BlackBoxDesign",
    "BlackBoxExperiment",
    "BlackBoxResult",
    "BlackBoxSelfTestReport",
    "CellObservation",
    "ChoiceProvider",
    "SyntheticChoiceProvider",
    "blackbox_selftest",
]
