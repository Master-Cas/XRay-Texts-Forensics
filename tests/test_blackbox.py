from __future__ import annotations

import pytest

from xray_text_forensics.blackbox import (
    BlackBoxDesign,
    BlackBoxExperiment,
    SyntheticChoiceProvider,
    blackbox_selftest,
)


def small_design() -> BlackBoxDesign:
    return BlackBoxDesign(
        prefixes=["p0", "p1", "p2", "p3", "p4", "p5"],
        contexts=["k0", "k1", "k2", "k3", "k4", "k5"],
        candidates=["a", "b", "c", "d"],
        samples_per_cell=35,
        permutation_count=199,
        alpha=0.01,
        seed=12345,
    )


def test_design_rejects_duplicate_contexts() -> None:
    with pytest.raises(ValueError, match="contexts must be unique"):
        BlackBoxDesign(
            prefixes=["p0", "p1", "p2"],
            contexts=["k", "k", "x", "y"],
            candidates=["a", "b"],
        )


def test_synthetic_on_off_validation() -> None:
    report = blackbox_selftest(
        permutation_count=199,
        samples_per_cell=35,
        alpha=0.01,
    )
    assert report.off.significant is False
    assert report.on.significant is True
    assert report.validated is True


def test_results_are_reproducible() -> None:
    design = small_design()
    experiment = BlackBoxExperiment(design)
    provider = SyntheticChoiceProvider(
        watermark_on=True,
        key=b"fixed",
        seed=design.seed,
    )
    first = experiment.run(provider)
    second = experiment.run(provider)
    assert first.statistic == second.statistic
    assert first.p_value == second.p_value
    assert first.context_candidate_residuals == second.context_candidate_residuals


def test_provider_must_return_candidate() -> None:
    class InvalidProvider:
        provider_id = "invalid"
        model_id = "invalid"

        def choose(self, **kwargs) -> str:
            del kwargs
            return "not-a-candidate"

    experiment = BlackBoxExperiment(small_design())
    with pytest.raises(ValueError, match="outside candidate set"):
        experiment.collect(InvalidProvider())


def test_prefix_preferences_do_not_trigger_alignment_by_themselves() -> None:
    design = small_design()
    result = BlackBoxExperiment(design).run(
        SyntheticChoiceProvider(watermark_on=False, seed=design.seed)
    )
    assert result.significant is False
