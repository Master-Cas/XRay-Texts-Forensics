"""Deterministic balanced experiment design."""

from __future__ import annotations

import random
import string
from uuid import uuid4

from .models import BlackBoxDesign, PromptCell


def build_design(
    *,
    prefixes: list[str],
    contexts: list[str],
    choices: list[str],
    repeats: int = 20,
    seed: int = 0,
    experiment_id: str | None = None,
) -> BlackBoxDesign:
    if not prefixes:
        raise ValueError("at least one prefix is required")
    if not contexts:
        raise ValueError("at least one context is required")
    if len(choices) < 2:
        raise ValueError("at least two forced choices are required")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")

    experiment_id = experiment_id or f"bb_{uuid4().hex}"
    prefix_map = {f"p{index:02d}": value for index, value in enumerate(prefixes)}
    context_map = {f"k{index:02d}": value for index, value in enumerate(contexts)}
    cells = [
        PromptCell(
            experiment_id=experiment_id,
            prefix_id=prefix_id,
            context_id=context_id,
            prefix=prefix,
            context=context,
            choices=choices,
        )
        for prefix_id, prefix in prefix_map.items()
        for context_id, context in context_map.items()
    ]
    return BlackBoxDesign(
        experiment_id=experiment_id,
        prefixes=prefix_map,
        contexts=context_map,
        choices=choices,
        repeats=repeats,
        seed=seed,
        cells=cells,
    )


def default_validation_design(
    *,
    seed: int = 314159,
    repeats: int = 24,
) -> BlackBoxDesign:
    prefixes = [
        "Complete the following choice consistently:",
        "Select exactly one permitted word:",
        "Return only one item from the allowed set:",
        "Choose one valid token and nothing else:",
        "For this constrained task, answer with one choice:",
        "Use exactly one of the listed alternatives:",
        "Respond with a single allowed word:",
        "Make one forced choice from the vocabulary:",
    ]
    contexts = _nonrepeating_digit_contexts(count=12, seed=seed, length=15)
    choices = ["amber", "berry", "cedar", "delta", "ember", "fjord"]
    return build_design(
        prefixes=prefixes,
        contexts=contexts,
        choices=choices,
        repeats=repeats,
        seed=seed,
        experiment_id=f"bb-validation-{seed}",
    )


def _nonrepeating_digit_contexts(*, count: int, seed: int, length: int) -> list[str]:
    rng = random.Random(seed)
    alphabet = string.digits
    contexts: set[str] = set()
    while len(contexts) < count:
        chars: list[str] = []
        while len(chars) < length:
            candidate = rng.choice(alphabet)
            if chars and candidate == chars[-1]:
                continue
            chars.append(candidate)
        contexts.add("".join(chars))
    return sorted(contexts)
