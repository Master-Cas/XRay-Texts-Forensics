"""Reference keyed red/green watermark detector.

This module exists to validate XRay's known-key detector architecture. It is not SynthID.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Sequence

from pydantic import BaseModel, Field
from scipy.stats import norm

from xray_text_forensics.core import Evidence, EvidenceFamily, EvidenceStatus
from xray_text_forensics.detectors.base import (
    AnalysisContext,
    Detector,
    DetectorDescriptor,
    DetectorRequirements,
)

from .base import SecretProvider, StableWordTokenizer, WatermarkTokenizer


class RedGreenConfig(BaseModel):
    gamma: float = Field(default=0.5, gt=0.0, lt=1.0)
    context_width: int = Field(default=4, ge=1, le=32)
    threshold_z: float = 4.0
    min_scored_tokens: int = Field(default=50, ge=1)
    mask_repeated_contexts: bool = True


class ReferenceRedGreenDetector(Detector):
    """Score token choices against a keyed pseudo-random green list."""

    def __init__(self, config: RedGreenConfig | None = None) -> None:
        self.config = config or RedGreenConfig()

    @property
    def descriptor(self) -> DetectorDescriptor:
        return DetectorDescriptor(
            detector_id="watermark.redgreen.reference",
            version="1.0.0",
            family=EvidenceFamily.WATERMARK,
            requirements=DetectorRequirements(
                raw_unicode=True,
                tokenizer=True,
                secret_key=True,
            ),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        selected = context.preferred_text_view()
        if selected is None:
            return [self._not_testable(context, "No usable text view is available.")]

        provider = context.resources.get("secret_provider")
        secret_ref = context.resources.get("secret_ref")
        tokenizer = context.resources.get("watermark_tokenizer")

        if not isinstance(secret_ref, str) or not secret_ref:
            return [self._not_testable(context, "No secret reference was supplied.")]
        if provider is None or not hasattr(provider, "get_secret"):
            return [self._not_testable(context, "No SecretProvider is available.")]
        if tokenizer is None or not hasattr(tokenizer, "encode"):
            return [self._not_testable(context, "No watermark tokenizer is available.")]

        secret_provider: SecretProvider = provider
        watermark_tokenizer: WatermarkTokenizer = tokenizer
        secret = secret_provider.get_secret(secret_ref)
        if not secret:
            return [
                self._not_testable(
                    context,
                    f"Secret reference {secret_ref!r} could not be resolved.",
                )
            ]

        view, text = selected
        token_ids = watermark_tokenizer.encode(text)
        score = score_token_ids(token_ids, secret, self.config)

        if score["scored_tokens"] < self.config.min_scored_tokens:
            return [
                Evidence(
                    artifact_id=context.artifact.artifact_id,
                    family=EvidenceFamily.WATERMARK,
                    status=EvidenceStatus.INSUFFICIENT_DATA,
                    detector_id=self.descriptor.detector_id,
                    detector_version=self.descriptor.version,
                    finding="KNOWN_KEY_RED_GREEN_WATERMARK",
                    reason=(
                        f"Only {score['scored_tokens']} eligible tokens; "
                        f"minimum is {self.config.min_scored_tokens}."
                    ),
                    derived_view_id=view.view_id,
                    parameters=self._parameters(score, secret_ref, watermark_tokenizer),
                )
            ]

        detected = float(score["z_score"]) >= self.config.threshold_z
        return [
            Evidence(
                artifact_id=context.artifact.artifact_id,
                family=EvidenceFamily.WATERMARK,
                status=EvidenceStatus.DETECTED if detected else EvidenceStatus.NOT_DETECTED,
                detector_id=self.descriptor.detector_id,
                detector_version=self.descriptor.version,
                finding="KNOWN_KEY_RED_GREEN_WATERMARK",
                derived_view_id=view.view_id,
                parameters=self._parameters(score, secret_ref, watermark_tokenizer),
            )
        ]

    def _not_testable(self, context: AnalysisContext, reason: str) -> Evidence:
        return Evidence(
            artifact_id=context.artifact.artifact_id,
            family=EvidenceFamily.WATERMARK,
            status=EvidenceStatus.NOT_TESTABLE,
            detector_id=self.descriptor.detector_id,
            detector_version=self.descriptor.version,
            finding="KNOWN_KEY_RED_GREEN_WATERMARK",
            reason=reason,
        )

    def _parameters(
        self,
        score: dict[str, int | float],
        secret_ref: str,
        tokenizer: WatermarkTokenizer,
    ) -> dict[str, int | float | str | bool]:
        return {
            **score,
            "gamma": self.config.gamma,
            "context_width": self.config.context_width,
            "threshold_z": self.config.threshold_z,
            "mask_repeated_contexts": self.config.mask_repeated_contexts,
            "secret_ref": secret_ref,
            "tokenizer_id": tokenizer.tokenizer_id,
            "scheme": "xray-reference-redgreen-v1",
            "interpretation": (
                "Reference known-key red/green detector result. This is not SynthID "
                "and must not be presented as provider provenance."
            ),
        }


def score_token_ids(
    token_ids: Sequence[int],
    secret: bytes,
    config: RedGreenConfig,
) -> dict[str, int | float]:
    width = config.context_width
    green_count = 0
    scored = 0
    repeated_skipped = 0
    seen_contexts: set[tuple[int, ...]] = set()

    for index in range(width, len(token_ids)):
        context = tuple(token_ids[index - width : index])
        if config.mask_repeated_contexts and context in seen_contexts:
            repeated_skipped += 1
            continue
        seen_contexts.add(context)
        token_id = token_ids[index]
        scored += 1
        green_count += int(_is_green(context, token_id, secret, config.gamma))

    expected = scored * config.gamma
    variance = scored * config.gamma * (1.0 - config.gamma)
    z_score = (green_count - expected) / math.sqrt(variance) if variance else 0.0
    p_value = float(norm.sf(z_score)) if scored else 1.0

    return {
        "scored_tokens": scored,
        "green_tokens": green_count,
        "repeated_contexts_skipped": repeated_skipped,
        "green_fraction": green_count / scored if scored else 0.0,
        "z_score": z_score,
        "one_sided_p_value": p_value,
    }


def _is_green(
    context: Sequence[int],
    token_id: int,
    secret: bytes,
    gamma: float,
) -> bool:
    message = b"".join(value.to_bytes(8, "big", signed=False) for value in context)
    message += token_id.to_bytes(8, "big", signed=False)
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    draw = int.from_bytes(digest[:8], "big", signed=False) / float(1 << 64)
    return draw < gamma


def generate_reference_watermarked_text(
    *,
    secret: bytes,
    token_count: int = 180,
    config: RedGreenConfig | None = None,
    candidate_count: int = 64,
) -> str:
    """Generate deterministic test text with strong reference red/green signal."""

    config = config or RedGreenConfig()
    tokenizer = StableWordTokenizer()
    seed = [f"seed{index}" for index in range(config.context_width)]
    words = list(seed)
    ids = [tokenizer.token_id(word) for word in words]

    while len(words) < token_count:
        context = tuple(ids[-config.context_width :])
        position = len(words)
        candidates = [f"token{position}x{index}" for index in range(candidate_count)]
        candidate_ids = [(word, tokenizer.token_id(word)) for word in candidates]
        chosen_word, chosen_id = candidate_ids[0]
        for word, token_id in candidate_ids:
            if _is_green(context, token_id, secret, config.gamma):
                chosen_word, chosen_id = word, token_id
                break
        words.append(chosen_word)
        ids.append(chosen_id)

    return " ".join(words)
