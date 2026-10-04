"""Typed models for corpus and linguistic analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CorpusDocument(BaseModel):
    document_id: str
    text: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ContextUnit(BaseModel):
    document_id: str
    context_id: str
    kind: str
    text: str
    tokens: list[str]


class CorpusSnapshot(BaseModel):
    name: str
    document_count: int
    context_count: int
    token_count: int
    vocabulary_size: int


class AssociationMetrics(BaseModel):
    term_a: str
    term_b: str
    cooccurrence: int
    contexts_a: int
    contexts_b: int
    context_count: int
    cosine: float
    dice: float
    jaccard: float
    equivalence: float
    inclusion: float
    mutual_information: float


class SpecificityResult(BaseModel):
    term: str
    count_a: int
    count_b: int
    total_a: int
    total_b: int
    log2_fold_change_a_over_b: float
    chi_square: float
    direction: str


class CorpusComparison(BaseModel):
    corpus_a: CorpusSnapshot
    corpus_b: CorpusSnapshot
    cosine_similarity: float
    intertextual_distance: float
    specificity: list[SpecificityResult]
