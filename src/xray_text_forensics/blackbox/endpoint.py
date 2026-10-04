"""Endpoint adapter contract plus a controlled synthetic validation endpoint."""

from __future__ import annotations

import hashlib
import hmac
import math
import random
from typing import Protocol

from .models import BlackBoxDesign, BlackBoxObservation, PromptCell


class ChoiceEndpoint(Protocol):
    def choose(self, cell: PromptCell, repeat_index: int) -> str: ...


class SyntheticChoiceEndpoint:
    """Same base sampler with optional keyed context-choice tilt.

    The OFF and ON variants share the same prefix preferences and random sampling logic.
    Only the keyed context-choice tilt changes.
    """

    def __init__(
        self,
        *,
        secret: bytes | None,
        seed: int,
        watermark_strength: float = 2.8,
        prefix_bias_strength: float = 2.2,
    ) -> None:
        self.secret = secret
        self.seed = seed
        self.watermark_strength = watermark_strength
        self.prefix_bias_strength = prefix_bias_strength

    def choose(self, cell: PromptCell, repeat_index: int) -> str:
        logits = [
            self._prefix_logit(cell.prefix_id, choice)
            + self._watermark_logit(cell.context, choice)
            for choice in cell.choices
        ]
        probabilities = _softmax(logits)
        rng = random.Random(
            _stable_int(
                f"{self.seed}|{cell.experiment_id}|{cell.prefix_id}|"
                f"{cell.context_id}|{repeat_index}"
            )
        )
        draw = rng.random()
        cumulative = 0.0
        for choice, probability in zip(cell.choices, probabilities, strict=True):
            cumulative += probability
            if draw <= cumulative:
                return choice
        return cell.choices[-1]

    def _prefix_logit(self, prefix_id: str, choice: str) -> float:
        raw = _unit_hash(f"prefix|{self.seed}|{prefix_id}|{choice}")
        return self.prefix_bias_strength * (2.0 * raw - 1.0)

    def _watermark_logit(self, context: str, choice: str) -> float:
        if self.secret is None:
            return 0.0
        digest = hmac.new(
            self.secret,
            f"{context}|{choice}".encode(),
            hashlib.sha256,
        ).digest()
        bit = digest[0] & 1
        return self.watermark_strength if bit else -self.watermark_strength


def collect_observations(
    design: BlackBoxDesign,
    endpoint: ChoiceEndpoint,
) -> list[BlackBoxObservation]:
    rows: list[BlackBoxObservation] = []
    for cell in design.cells:
        for repeat_index in range(design.repeats):
            raw = endpoint.choose(cell, repeat_index)
            valid = raw in cell.choices
            rows.append(
                BlackBoxObservation(
                    experiment_id=design.experiment_id,
                    prefix_id=cell.prefix_id,
                    context_id=cell.context_id,
                    repeat_index=repeat_index,
                    choice=raw if valid else None,
                    allowed_choices=cell.choices,
                    valid=valid,
                    raw_output=raw,
                )
            )
    return rows


def _softmax(logits: list[float]) -> list[float]:
    maximum = max(logits)
    exps = [math.exp(value - maximum) for value in logits]
    total = sum(exps)
    return [value / total for value in exps]


def _stable_int(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def _unit_hash(value: str) -> float:
    return _stable_int(value) / float(1 << 64)
