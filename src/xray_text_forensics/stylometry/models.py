"""Typed models for reference-corpus similarity."""

from __future__ import annotations

from pydantic import BaseModel, Field

from xray_text_forensics.corpus.models import CorpusDocument


class StyleFingerprint(BaseModel):
    token_count: int
    type_token_ratio: float
    sentence_count: int
    mean_sentence_tokens: float
    std_sentence_tokens: float
    paragraph_count: int
    mean_paragraph_tokens: float
    char_count: int
    comma_per_kchar: float
    semicolon_per_kchar: float
    colon_per_kchar: float
    dash_per_kchar: float
    question_per_kchar: float
    exclamation_per_kchar: float
    parentheses_per_kchar: float
    quote_per_kchar: float
    digit_ratio: float
    uppercase_ratio: float


class ReferenceMetadata(BaseModel):
    label: str
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    language: str | None = None
    topic: str | None = None
    source: str
    license: str | None = None
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ReferenceSet(BaseModel):
    metadata: ReferenceMetadata
    documents: list[CorpusDocument]


class ReferenceManifest(BaseModel):
    label: str
    document_count: int
    manifest_sha256: str
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    language: str | None = None
    topic: str | None = None
    source: str
    license: str | None = None


class ReferenceSimilarity(BaseModel):
    label: str
    manifest_sha256: str
    document_count: int
    style_similarity: float
    char_svd_similarity: float
    content_similarity: float
    interpretation: str


class ReferenceComparisonReport(BaseModel):
    suspect_sha256: str
    comparisons: list[ReferenceSimilarity]
    scientific_note: str = (
        "These are reference-corpus similarities, not authorship probabilities or "
        "provider-provenance claims."
    )
