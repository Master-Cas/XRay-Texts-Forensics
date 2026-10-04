"""Controlled ON/OFF validation of the black-box protocol."""

from __future__ import annotations

from .analyze import analyze_observations
from .design import default_validation_design
from .endpoint import SyntheticChoiceEndpoint, collect_observations
from .models import BlackBoxValidationResult


def run_synthetic_validation(
    *,
    permutations: int = 499,
    seed: int = 314159,
    alpha: float = 0.01,
) -> BlackBoxValidationResult:
    design = default_validation_design(seed=seed)
    off_endpoint = SyntheticChoiceEndpoint(secret=None, seed=seed)
    on_endpoint = SyntheticChoiceEndpoint(
        secret=b"xray-controlled-blackbox-validation-key",
        seed=seed,
    )

    off_rows = collect_observations(design, off_endpoint)
    on_rows = collect_observations(design, on_endpoint)
    off_result = analyze_observations(
        off_rows,
        permutations=permutations,
        seed=seed + 1,
    )
    on_result = analyze_observations(
        on_rows,
        permutations=permutations,
        seed=seed + 1,
    )
    passed = off_result.p_value > alpha and on_result.p_value <= alpha
    return BlackBoxValidationResult(
        off_result=off_result,
        on_result=on_result,
        alpha=alpha,
        passed=passed,
        criterion=(
            "Same synthetic base sampler: watermark OFF must not reject at alpha, "
            "watermark ON must reject at or below alpha."
        ),
    )
