from __future__ import annotations

from xray_text_forensics.blackbox import (
    SyntheticChoiceEndpoint,
    analyze_observations,
    build_design,
    collect_observations,
    default_validation_design,
    run_synthetic_validation,
)
from xray_text_forensics.blackbox.io import (
    load_observations_jsonl,
    save_observations_jsonl,
)


def test_default_design_is_balanced_and_contexts_unique() -> None:
    design = default_validation_design(seed=42, repeats=3)
    assert len(design.cells) == len(design.prefixes) * len(design.contexts)
    assert len(set(design.contexts.values())) == len(design.contexts)
    assert all(len(context) == 15 for context in design.contexts.values())


def test_build_design_rejects_duplicate_contexts() -> None:
    try:
        build_design(
            prefixes=["a"],
            contexts=["123", "123"],
            choices=["x", "y"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate contexts must fail")


def test_synthetic_validation_separates_off_and_on() -> None:
    validation = run_synthetic_validation(permutations=199, seed=314159, alpha=0.01)
    assert validation.passed
    assert validation.off_result.p_value > 0.01
    assert validation.on_result.p_value <= 0.01
    assert validation.on_result.statistic > validation.off_result.statistic


def test_analysis_is_deterministic_for_fixed_seed() -> None:
    design = default_validation_design(seed=7, repeats=8)
    rows = collect_observations(
        design,
        SyntheticChoiceEndpoint(secret=b"key", seed=7),
    )
    first = analyze_observations(rows, permutations=99, seed=123)
    second = analyze_observations(rows, permutations=99, seed=123)
    assert first.statistic == second.statistic
    assert first.p_value == second.p_value


def test_prefix_bias_without_context_key_does_not_automatically_trigger() -> None:
    design = default_validation_design(seed=2718, repeats=16)
    rows = collect_observations(
        design,
        SyntheticChoiceEndpoint(
            secret=None,
            seed=2718,
            prefix_bias_strength=4.0,
        ),
    )
    result = analyze_observations(rows, permutations=199, seed=5)
    assert result.p_value > 0.01


def test_jsonl_roundtrip(tmp_path) -> None:
    design = default_validation_design(seed=11, repeats=2)
    rows = collect_observations(
        design,
        SyntheticChoiceEndpoint(secret=None, seed=11),
    )
    path = tmp_path / "observations.jsonl"
    save_observations_jsonl(path, rows)
    loaded = load_observations_jsonl(path)
    assert loaded == rows
