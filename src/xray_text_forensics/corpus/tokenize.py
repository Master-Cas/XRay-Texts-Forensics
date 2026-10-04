"""Deterministic lightweight tokenization and context segmentation."""

from __future__ import annotations

import re

from .models import ContextUnit, CorpusDocument

_WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def tokenize(text: str) -> list[str]:
    return [match.group(0).casefold() for match in _WORD_RE.finditer(text)]


def paragraph_contexts(document: CorpusDocument) -> list[ContextUnit]:
    contexts: list[ContextUnit] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", document.text) if part.strip()]
    if not paragraphs and document.text.strip():
        paragraphs = [document.text.strip()]

    for index, paragraph in enumerate(paragraphs):
        contexts.append(
            ContextUnit(
                document_id=document.document_id,
                context_id=f"{document.document_id}:p:{index}",
                kind="paragraph",
                text=paragraph,
                tokens=tokenize(paragraph),
            )
        )
    return contexts


def sentence_contexts(document: CorpusDocument) -> list[ContextUnit]:
    contexts: list[ContextUnit] = []
    parts = [part.strip() for part in _SENTENCE_RE.split(document.text) if part.strip()]
    for index, sentence in enumerate(parts):
        contexts.append(
            ContextUnit(
                document_id=document.document_id,
                context_id=f"{document.document_id}:s:{index}",
                kind="sentence",
                text=sentence,
                tokens=tokenize(sentence),
            )
        )
    return contexts
