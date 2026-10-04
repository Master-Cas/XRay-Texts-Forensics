"""Deterministic text stress transformations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StressTransform:
    transform_id: str
    description: str
    apply: Callable[[str], str]


def unicode_nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def whitespace_canonical(text: str) -> str:
    return " ".join(text.split())


def casefold_text(text: str) -> str:
    return text.casefold()


def strip_punctuation(text: str) -> str:
    return "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in text
    )


def replace_every_nth_token(text: str, n: int) -> str:
    if n < 1:
        raise ValueError("n must be >= 1")
    counter = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        if counter % n == 0:
            return f"xrayrewrite{counter}"
        return match.group(0)

    return re.sub(r"\S+", replace, text)


def delete_every_nth_token(text: str, n: int) -> str:
    if n < 2:
        raise ValueError("n must be >= 2")
    tokens = text.split()
    kept = [token for index, token in enumerate(tokens, 1) if index % n != 0]
    return " ".join(kept)


def default_stress_transforms() -> tuple[StressTransform, ...]:
    return (
        StressTransform(
            "unicode_nfkc",
            "Unicode NFKC normalization.",
            unicode_nfkc,
        ),
        StressTransform(
            "whitespace_canonical",
            "Collapse whitespace to single spaces.",
            whitespace_canonical,
        ),
        StressTransform(
            "casefold",
            "Unicode-aware case folding.",
            casefold_text,
        ),
        StressTransform(
            "strip_punctuation",
            "Replace Unicode punctuation with spaces.",
            strip_punctuation,
        ),
        StressTransform(
            "replace_every_3rd_token",
            "Deterministically replace every third whitespace token.",
            lambda text: replace_every_nth_token(text, 3),
        ),
        StressTransform(
            "delete_every_5th_token",
            "Deterministically delete every fifth whitespace token.",
            lambda text: delete_every_nth_token(text, 5),
        ),
    )
