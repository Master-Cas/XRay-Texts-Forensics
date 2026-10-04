"""Black-box statistical audit framework."""

from .experiment import BlackBoxExperiment, blackbox_selftest
from .io import load_design, load_observations_jsonl, save_design, save_observations_jsonl
from .models import (
    BlackBoxDesign,
    BlackBoxResult,
    BlackBoxSelfTestReport,
    CellObservation,
)
from .providers import (
    ChoiceProvider,
    ProviderIdentity,
    RecordedProviderIdentity,
    SyntheticChoiceProvider,
)

__all__ = [
    "BlackBoxDesign",
    "BlackBoxExperiment",
    "BlackBoxResult",
    "BlackBoxSelfTestReport",
    "CellObservation",
    "ChoiceProvider",
    "ProviderIdentity",
    "RecordedProviderIdentity",
    "SyntheticChoiceProvider",
    "blackbox_selftest",
    "load_design",
    "load_observations_jsonl",
    "save_design",
    "save_observations_jsonl",
]
