from __future__ import annotations

import pytest

from xray_text_forensics.calibration import (
    CalibrationConfig,
    ScoreSample,
    calibrate,
    evaluate,
)


def controls(n: int = 200) -> list[ScoreSample]:
    return [
        ScoreSample(
            sample_id=f"neg-{index}",
            label=False,
            score=index / n,
            length=50 + (index % 600),
        )
        for index in range(n)
    ]


def manifest_for(samples: list[ScoreSample], target_fpr: float = 0.01):
    return calibrate(
        samples,
        config=CalibrationConfig(
            target_fpr=target_fpr,
            min_control_samples=len(samples),
        ),
        detector_id="demo.detector",
        detector_version="1.0",
        dataset_id="demo",
        dataset_version="v1",
    )


def test_calibration_rejects_positive_samples() -> None:
    samples = controls(100)
    samples[0] = samples[0].model_copy(update={"label": True})
    with pytest.raises(ValueError, match="negative controls"):
        manifest_for(samples)


def test_calibration_meets_empirical_fpr_target() -> None:
    manifest = manifest_for(controls(200), 0.01)
    assert manifest.dev_empirical_fpr <= 0.01
    assert manifest.dev_false_positives <= 2


def test_calibration_digest_is_order_independent() -> None:
    samples = controls(120)
    first = manifest_for(samples)
    second = manifest_for(list(reversed(samples)))
    assert first.controls_sha256 == second.controls_sha256
    assert first.threshold == second.threshold


def test_held_out_evaluation_does_not_change_threshold() -> None:
    manifest = manifest_for(controls(200))
    threshold = manifest.threshold
    test = [
        ScoreSample(sample_id=f"n{i}", label=False, score=0.1, length=100)
        for i in range(50)
    ] + [
        ScoreSample(sample_id=f"p{i}", label=True, score=2.0, length=300)
        for i in range(50)
    ]
    report = evaluate(test, manifest)
    assert report.manifest.threshold == threshold
    assert report.tpr == 1.0
    assert report.fpr == 0.0
    assert report.roc_auc == 1.0


def test_length_buckets_report_separate_performance() -> None:
    manifest = manifest_for(controls(200))
    test = [
        ScoreSample(sample_id="short-neg", label=False, score=0.0, length=50),
        ScoreSample(sample_id="short-pos", label=True, score=2.0, length=60),
        ScoreSample(sample_id="long-neg", label=False, score=0.0, length=600),
        ScoreSample(sample_id="long-pos", label=True, score=2.0, length=700),
    ]
    report = evaluate(test, manifest)
    buckets = {bucket.label: bucket for bucket in report.length_buckets}
    assert buckets["0-64"].tpr == 1.0
    assert buckets["0-64"].fpr == 0.0
    assert buckets["513+"].tpr == 1.0


def test_lower_scores_can_be_positive() -> None:
    samples = [
        ScoreSample(sample_id=f"n{i}", label=False, score=1.0 + i / 100, length=100)
        for i in range(100)
    ]
    manifest = calibrate(
        samples,
        config=CalibrationConfig(
            target_fpr=0.01,
            higher_is_positive=False,
            min_control_samples=100,
        ),
        detector_id="low.detector",
        detector_version="1",
        dataset_id="demo",
        dataset_version="1",
    )
    test = [
        ScoreSample(sample_id="p", label=True, score=-1.0, length=100),
        ScoreSample(sample_id="n", label=False, score=2.5, length=100),
    ]
    report = evaluate(test, manifest)
    assert report.tpr == 1.0
    assert report.fpr == 0.0
