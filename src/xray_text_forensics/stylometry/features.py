"""Interpretable structural style features."""

from __future__ import annotations

import statistics

from xray_text_forensics.corpus.models import CorpusDocument
from xray_text_forensics.corpus.tokenize import paragraph_contexts, sentence_contexts, tokenize

from .models import StyleFingerprint

STYLE_FIELDS: tuple[str, ...] = (
    "type_token_ratio",
    "sentence_count",
    "mean_sentence_tokens",
    "std_sentence_tokens",
    "paragraph_count",
    "mean_paragraph_tokens",
    "comma_per_kchar",
    "semicolon_per_kchar",
    "colon_per_kchar",
    "dash_per_kchar",
    "question_per_kchar",
    "exclamation_per_kchar",
    "parentheses_per_kchar",
    "quote_per_kchar",
    "digit_ratio",
    "uppercase_ratio",
)


def extract_style_fingerprint(text: str) -> StyleFingerprint:
    document = CorpusDocument(document_id="style", text=text)
    tokens = tokenize(text)
    sentences = sentence_contexts(document)
    paragraphs = paragraph_contexts(document)
    sentence_lengths = [len(context.tokens) for context in sentences]
    paragraph_lengths = [len(context.tokens) for context in paragraphs]
    char_count = len(text)

    return StyleFingerprint(
        token_count=len(tokens),
        type_token_ratio=len(set(tokens)) / len(tokens) if tokens else 0.0,
        sentence_count=len(sentences),
        mean_sentence_tokens=_mean(sentence_lengths),
        std_sentence_tokens=(
            statistics.pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
        ),
        paragraph_count=len(paragraphs),
        mean_paragraph_tokens=_mean(paragraph_lengths),
        char_count=char_count,
        comma_per_kchar=_rate(text.count(","), char_count),
        semicolon_per_kchar=_rate(text.count(";"), char_count),
        colon_per_kchar=_rate(text.count(":"), char_count),
        dash_per_kchar=_rate(text.count("-") + text.count("—") + text.count("–"), char_count),
        question_per_kchar=_rate(text.count("?"), char_count),
        exclamation_per_kchar=_rate(text.count("!"), char_count),
        parentheses_per_kchar=_rate(text.count("(") + text.count(")"), char_count),
        quote_per_kchar=_rate(
            text.count('"') + text.count("“") + text.count("”") + text.count("«") + text.count("»"),
            char_count,
        ),
        digit_ratio=(
            sum(character.isdigit() for character in text) / char_count if char_count else 0.0
        ),
        uppercase_ratio=(
            sum(character.isupper() for character in text) / char_count if char_count else 0.0
        ),
    )


def fingerprint_vector(fingerprint: StyleFingerprint) -> list[float]:
    return [float(getattr(fingerprint, field)) for field in STYLE_FIELDS]


def _mean(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _rate(count: int, char_count: int) -> float:
    return 1000.0 * count / char_count if char_count else 0.0
