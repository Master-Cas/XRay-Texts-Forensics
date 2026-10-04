"""Provider contracts and controlled synthetic providers."""

from __future__ import annotations

import hashlib
import hmac
import math
from typing import Protocol


class ChoiceProvider(Protocol):
    """Provider capable of one forced-choice completion."""

    @property
    def provider_id(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    def choose(
        self,
        *,
        prefix: str,
        context: str,
        candidates: list[str],
        sample_index: int,
    ) -> str: ...


class SyntheticChoiceProvider:
    """Controlled same-base provider with optional keyed context bias.

    Prefix-specific baseline preferences are always present. In ON mode, a keyed
    context chooses the same favored candidate across prefixes.
    """

    def __init__(
        self,
        *,
        watermark_on: bool,
        key: bytes = b"xray-blackbox-selftest",
        signal_strength: float = 2.4,
        seed: int = 20261004,
    ) -> None:
        self.watermark_on = watermark_on
        self.key = key
        self.signal_strength = signal_strength
        self.seed = seed

    @property
    def provider_id(self) -> str:
        return "xray.synthetic"

    @property
    def model_id(self) -> str:
        return "choice-bias-on" if self.watermark_on else "choice-bias-off"

    def choose(
        self,
        *,
        prefix: str,
        context: str,
        candidates: list[str],
        sample_index: int,
    ) -> str:
        if not candidates:
            raise ValueError("candidates cannot be empty")

        logits = [self._prefix_logit(prefix, candidate) for candidate in candidates]
        if self.watermark_on:
            favored = self._favored_candidate(context, len(candidates))
            logits[favored] += self.signal_strength

        probabilities = _softmax(logits)
        draw = self._draw(prefix, context, sample_index)
        cumulative = 0.0
        for candidate, probability in zip(candidates, probabilities, strict=True):
            cumulative += probability
            if draw < cumulative:
                return candidate
        return candidates[-1]

    def _prefix_logit(self, prefix: str, candidate: str) -> float:
        digest = hashlib.sha256(
            f"{self.seed}|prefix|{prefix}|{candidate}".encode("utf-8")
        ).digest()
        unit = int.from_bytes(digest[:8], "big") / float(1 << 64)
        return (unit - 0.5) * 1.6

    def _favored_candidate(self, context: str, candidate_count: int) -> int:
        digest = hmac.new(self.key, context.encode("utf-8"), hashlib.sha256).digest()
        return int.from_bytes(digest[:8], "big") % candidate_count

    def _draw(self, prefix: str, context: str, sample_index: int) -> float:
        digest = hashlib.sha256(
            (
                f"{self.seed}|draw|{prefix}|{context}|{sample_index}|"
                f"{int(self.watermark_on)}"
            ).encode("utf-8")
        ).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _softmax(logits: list[float]) -> list[float]:
    maximum = max(logits)
    exponentials = [math.exp(value - maximum) for value in logits]
    total = sum(exponentials)
    return [value / total for value in exponentials]
