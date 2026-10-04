"""Empirical threshold calibration and held-out evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from uuid import uuid4

import numpy as np
from scipy.stats import norm
from sklearn.metrics import roc_auc_score

from .models import (
    CalibrationConfig,
    CalibrationManifest,
    EvaluationReport,
    LengthBucketMetrics,
    RateInterval,
    ScoreSample,
)


def calibrate(
    development_controls: list[ScoreSample],
    *,
    config: CalibrationConfig,
    detector_id: str,
    detector_version: str,
    dataset_id: str,
    dataset_version: str,
) -> CalibrationManifest:
    if len(development_controls) < config.min_control_samples:
        raise ValueError(
            f"Need at least {config.min_control_samples} development controls; "
            f"got {len(development_controls)}"
        )
    if any(sample.label for sample in development_controls):
        raise ValueError("Calibration input must contain negative controls only")

    scores = [sample.score for sample in development_controls]
    threshold = _select_threshold(scores, config.target_fpr, config.higher_is_positive)
    false_positives = sum(
        _predict(score, threshold, config.higher_is_positive) for score in scores
    )
    empirical_fpr = false_positives / len(scores)

    return CalibrationManifest(
        calibration_id=f"cal_{uuid4().hex}",
        detector_id=detector_id,
        detector_version=detector_version,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        target_fpr=config.target_fpr,
        higher_is_positive=config.higher_is_positive,
        threshold=threshold,
        dev_control_count=len(scores),
        dev_false_positives=false_positives,
        dev_empirical_fpr=empirical_fpr,
        controls_sha256=_controls_digest(development_controls),
    )


def evaluate(
    held_out_samples: list[ScoreSample],
    manifest: CalibrationManifest,
    *,
    confidence_level: float = 0.95,
) -> EvaluationReport:
    if not held_out_samples:
        raise ValueError("Held-out evaluation requires at least one sample")

    predictions = [
        _predict(sample.score, manifest.threshold, manifest.higher_is_positive)
        for sample in held_out_samples
    ]
    labels = [sample.label for sample in held_out_samples]

    tp = sum(pred and label for pred, label in zip(predictions, labels, strict=True))
    fp = sum(pred and not label for pred, label in zip(predictions, labels, strict=True))
    tn = sum(not pred and not label for pred, label in zip(predictions, labels, strict=True))
    fn = sum(not pred and label for pred, label in zip(predictions, labels, strict=True))

    positives = tp + fn
    negatives = tn + fp
    tpr = tp / positives if positives else 0.0
    fpr = fp / negatives if negatives else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tpr

    oriented_scores = [
        sample.score if manifest.higher_is_positive else -sample.score
        for sample in held_out_samples
    ]
    roc_auc = (
        float(roc_auc_score(labels, oriented_scores))
        if len(set(labels)) == 2
        else None
    )

    return EvaluationReport(
        manifest=manifest,
        sample_count=len(held_out_samples),
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        tpr=tpr,
        fpr=fpr,
        precision=precision,
        recall=recall,
        roc_auc=roc_auc,
        tpr_interval=_wilson_interval(tp, positives, confidence_level),
        fpr_interval=_wilson_interval(fp, negatives, confidence_level),
        length_buckets=_length_buckets(held_out_samples, predictions),
    )


def _select_threshold(
    scores: list[float],
    target_fpr: float,
    higher_is_positive: bool,
) -> float:
    allowed_false_positives = math.floor(target_fpr * len(scores) + 1e-12)
    unique = sorted(set(scores))

    if higher_is_positive:
        candidates = unique + [float(np.nextafter(max(unique), math.inf))]
        valid = [
            threshold
            for threshold in candidates
            if sum(score >= threshold for score in scores) <= allowed_false_positives
        ]
        return min(valid)

    candidates = [float(np.nextafter(min(unique), -math.inf))] + unique
    valid = [
        threshold
        for threshold in candidates
        if sum(score <= threshold for score in scores) <= allowed_false_positives
    ]
    return max(valid)


def _predict(score: float, threshold: float, higher_is_positive: bool) -> bool:
    return score >= threshold if higher_is_positive else score <= threshold


def _controls_digest(samples: list[ScoreSample]) -> str:
    payload = [
        {
            "sample_id": sample.sample_id,
            "score": sample.score,
            "length": sample.length,
            "metadata": sample.metadata,
        }
        for sample in sorted(samples, key=lambda item: item.sample_id)
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wilson_interval(
    numerator: int,
    denominator: int,
    confidence_level: float,
) -> RateInterval:
    if denominator == 0:
        return RateInterval(
            rate=0.0,
            lower=0.0,
            upper=1.0,
            numerator=numerator,
            denominator=denominator,
        )

    p = numerator / denominator
    z = float(norm.ppf(0.5 + confidence_level / 2.0))
    z2 = z * z
    denominator_term = 1.0 + z2 / denominator
    center = (p + z2 / (2.0 * denominator)) / denominator_term
    margin = (
        z
        * math.sqrt(
            p * (1.0 - p) / denominator + z2 / (4.0 * denominator * denominator)
        )
        / denominator_term
    )
    return RateInterval(
        rate=p,
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
        numerator=numerator,
        denominator=denominator,
    )


def _length_buckets(
    samples: list[ScoreSample],
    predictions: list[bool],
) -> list[LengthBucketMetrics]:
    specs: tuple[tuple[str, int, int | None], ...] = (
        ("0-64", 0, 64),
        ("65-128", 65, 128),
        ("129-256", 129, 256),
        ("257-512", 257, 512),
        ("513+", 513, None),
    )
    results: list[LengthBucketMetrics] = []

    for label, minimum, maximum in specs:
        selected = [
            (sample, prediction)
            for sample, prediction in zip(samples, predictions, strict=True)
            if sample.length >= minimum and (maximum is None or sample.length <= maximum)
        ]
        positives = sum(sample.label for sample, _ in selected)
        negatives = len(selected) - positives
        tp = sum(prediction and sample.label for sample, prediction in selected)
        fp = sum(prediction and not sample.label for sample, prediction in selected)

        results.append(
            LengthBucketMetrics(
                label=label,
                minimum=minimum,
                maximum=maximum,
                sample_count=len(selected),
                positive_count=positives,
                negative_count=negatives,
                tpr=tp / positives if positives else None,
                fpr=fp / negatives if negatives else None,
            )
        )

    return results
