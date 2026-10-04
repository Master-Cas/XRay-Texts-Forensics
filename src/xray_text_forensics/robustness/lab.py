"""Robustness measurements for the reference known-key watermark."""

from __future__ import annotations

import hashlib
import math
from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from xray_text_forensics.corpus.tokenize import tokenize
from xray_text_forensics.detectors.watermark.base import StableWordTokenizer
from xray_text_forensics.detectors.watermark.redgreen import (
    RedGreenConfig,
    score_token_ids,
)

from .models import (
    PreservationMetrics,
    RobustnessReport,
    StressResult,
    WatermarkMeasurement,
)
from .transforms import StressTransform, default_stress_transforms


def compare_texts(original: str, transformed: str) -> PreservationMetrics:
    original_tokens = tokenize(original)
    transformed_tokens = tokenize(transformed)
    original_set = set(original_tokens)
    transformed_set = set(transformed_tokens)
    union = original_set | transformed_set
    intersection = original_set & transformed_set
    token_jaccard = len(intersection) / len(union) if union else 1.0

    sequence_ratio = SequenceMatcher(
        None,
        original_tokens,
        transformed_tokens,
        autojunk=False,
    ).ratio()
    fivegram_survival = _ngram_survival(original_tokens, transformed_tokens, 5)
    lexical_tfidf_cosine = _tfidf_cosine(original, transformed)
    char_length_ratio = (
        len(transformed) / len(original)
        if original
        else 1.0 if not transformed else math.inf
    )

    return PreservationMetrics(
        original_token_count=len(original_tokens),
        transformed_token_count=len(transformed_tokens),
        token_jaccard=token_jaccard,
        token_sequence_ratio=sequence_ratio,
        fivegram_survival=fivegram_survival,
        lexical_tfidf_cosine=lexical_tfidf_cosine,
        char_length_ratio=char_length_ratio,
    )


def run_reference_watermark_stress(
    text: str,
    *,
    secret: bytes,
    threshold_z: float = 4.0,
    min_scored_tokens: int = 50,
    transforms: tuple[StressTransform, ...] | None = None,
) -> RobustnessReport:
    config = RedGreenConfig(
        threshold_z=threshold_z,
        min_scored_tokens=min_scored_tokens,
    )
    baseline = _measure(text, secret, config)
    results: list[StressResult] = []

    for transform in transforms or default_stress_transforms():
        transformed = transform.apply(text)
        measurement = _measure(transformed, secret, config)
        retained: bool | None
        if baseline.status == "INSUFFICIENT_DATA" or measurement.status == "INSUFFICIENT_DATA":
            retained = None
        else:
            retained = baseline.status == "DETECTED" and measurement.status == "DETECTED"

        results.append(
            StressResult(
                transform_id=transform.transform_id,
                transform_description=transform.description,
                transformed_sha256=_sha256(transformed),
                preservation=compare_texts(text, transformed),
                measurement=measurement,
                z_delta_from_baseline=measurement.z_score - baseline.z_score,
                detection_retained=retained,
            )
        )

    return RobustnessReport(
        original_sha256=_sha256(text),
        baseline=baseline,
        results=results,
    )


def _measure(
    text: str,
    secret: bytes,
    config: RedGreenConfig,
) -> WatermarkMeasurement:
    tokenizer = StableWordTokenizer()
    score = score_token_ids(tokenizer.encode(text), secret, config)
    scored = int(score["scored_tokens"])
    z_score = float(score["z_score"])

    if scored < config.min_scored_tokens:
        status = "INSUFFICIENT_DATA"
    elif z_score >= config.threshold_z:
        status = "DETECTED"
    else:
        status = "NOT_DETECTED"

    return WatermarkMeasurement(
        status=status,
        scored_tokens=scored,
        green_tokens=int(score["green_tokens"]),
        green_fraction=float(score["green_fraction"]),
        z_score=z_score,
        one_sided_p_value=float(score["one_sided_p_value"]),
        threshold_z=config.threshold_z,
        min_scored_tokens=config.min_scored_tokens,
    )


def _ngram_survival(original: list[str], transformed: list[str], n: int) -> float:
    if len(original) < n:
        return 1.0 if original == transformed else 0.0
    original_ngrams = {
        tuple(original[index : index + n])
        for index in range(len(original) - n + 1)
    }
    transformed_ngrams = {
        tuple(transformed[index : index + n])
        for index in range(max(0, len(transformed) - n + 1))
    }
    return len(original_ngrams & transformed_ngrams) / len(original_ngrams)


def _tfidf_cosine(original: str, transformed: str) -> float:
    if original == transformed:
        return 1.0
    if not original.strip() or not transformed.strip():
        return 0.0

    vectorizer = TfidfVectorizer(
        tokenizer=tokenize,
        token_pattern=None,
        lowercase=False,
        norm="l2",
    )
    matrix = vectorizer.fit_transform([original, transformed])
    return float(cosine_similarity(matrix[0], matrix[1])[0, 0])


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
