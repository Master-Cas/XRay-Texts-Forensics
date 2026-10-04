"""Interpretable corpus statistics and comparison primitives."""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

import numpy as np
from scipy.stats import chi2_contingency
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import (
    AssociationMetrics,
    ContextUnit,
    CorpusComparison,
    CorpusDocument,
    CorpusSnapshot,
    SpecificityResult,
)
from .tokenize import paragraph_contexts, sentence_contexts, tokenize


class CorpusEngine:
    """Build interpretable linguistic statistics from a document collection."""

    def __init__(
        self,
        documents: list[CorpusDocument],
        *,
        name: str = "corpus",
        context_kind: str = "sentence",
    ) -> None:
        if context_kind not in {"sentence", "paragraph"}:
            raise ValueError("context_kind must be 'sentence' or 'paragraph'")
        self.documents = documents
        self.name = name
        self.context_kind = context_kind
        self.contexts = self._build_contexts(documents, context_kind)
        self.tokens = [token for document in documents for token in tokenize(document.text)]
        self.term_counts = Counter(self.tokens)
        self.context_presence = Counter(
            term for context in self.contexts for term in set(context.tokens)
        )
        self.cooccurrence = self._build_cooccurrence(self.contexts)

    @staticmethod
    def _build_contexts(
        documents: list[CorpusDocument],
        context_kind: str,
    ) -> list[ContextUnit]:
        builder = sentence_contexts if context_kind == "sentence" else paragraph_contexts
        return [context for document in documents for context in builder(document)]

    @staticmethod
    def _build_cooccurrence(contexts: list[ContextUnit]) -> Counter[tuple[str, str]]:
        counts: Counter[tuple[str, str]] = Counter()
        for context in contexts:
            terms = sorted(set(context.tokens))
            for first, second in combinations(terms, 2):
                counts[(first, second)] += 1
        return counts

    def snapshot(self) -> CorpusSnapshot:
        return CorpusSnapshot(
            name=self.name,
            document_count=len(self.documents),
            context_count=len(self.contexts),
            token_count=len(self.tokens),
            vocabulary_size=len(self.term_counts),
        )

    def ngram_counts(self, n: int) -> Counter[tuple[str, ...]]:
        if n < 1:
            raise ValueError("n must be >= 1")
        counts: Counter[tuple[str, ...]] = Counter()
        for document in self.documents:
            tokens = tokenize(document.text)
            counts.update(tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1))
        return counts

    def association(self, term_a: str, term_b: str) -> AssociationMetrics:
        a = term_a.casefold()
        b = term_b.casefold()
        if a == b:
            raise ValueError("association requires two distinct terms")
        first, second = sorted((a, b))
        co = self.cooccurrence[(first, second)]
        freq_a = self.context_presence[a]
        freq_b = self.context_presence[b]
        total = len(self.contexts)

        cosine = co / math.sqrt(freq_a * freq_b) if freq_a and freq_b else 0.0
        dice = (2 * co) / (freq_a + freq_b) if freq_a + freq_b else 0.0
        union = freq_a + freq_b - co
        jaccard = co / union if union else 0.0
        equivalence = (co * co) / (freq_a * freq_b) if freq_a and freq_b else 0.0
        inclusion = co / min(freq_a, freq_b) if min(freq_a, freq_b) else 0.0
        mi = (
            math.log2((co * total) / (freq_a * freq_b))
            if co and total and freq_a and freq_b
            else 0.0
        )

        return AssociationMetrics(
            term_a=a,
            term_b=b,
            cooccurrence=co,
            contexts_a=freq_a,
            contexts_b=freq_b,
            context_count=total,
            cosine=cosine,
            dice=dice,
            jaccard=jaccard,
            equivalence=equivalence,
            inclusion=inclusion,
            mutual_information=mi,
        )

    def second_order_similarity(self, term_a: str, term_b: str) -> float:
        """Compare co-occurrence profiles, not direct co-occurrence."""

        a = term_a.casefold()
        b = term_b.casefold()
        vocabulary = sorted(self.term_counts)
        if a not in self.term_counts or b not in self.term_counts:
            return 0.0

        vector_a = np.array(
            [self._cooccurrence_value(a, term) if term != a else 0 for term in vocabulary],
            dtype=float,
        )
        vector_b = np.array(
            [self._cooccurrence_value(b, term) if term != b else 0 for term in vocabulary],
            dtype=float,
        )
        norm_a = float(np.linalg.norm(vector_a))
        norm_b = float(np.linalg.norm(vector_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(vector_a, vector_b) / (norm_a * norm_b))

    def _cooccurrence_value(self, first: str, second: str) -> int:
        if first == second:
            return 0
        return self.cooccurrence[tuple(sorted((first, second)))]

    def tfidf_document_matrix(self) -> tuple[np.ndarray, list[str]]:
        if not self.documents:
            return np.empty((0, 0)), []

        vectorizer = TfidfVectorizer(
            tokenizer=tokenize,
            token_pattern=None,
            lowercase=False,
            norm="l2",
        )
        matrix = vectorizer.fit_transform(document.text for document in self.documents)
        return matrix.toarray(), list(vectorizer.get_feature_names_out())

    def compare(self, other: CorpusEngine, *, top_n: int = 50) -> CorpusComparison:
        specificity = self.specificity_against(other, top_n=top_n)
        similarity = _corpus_tfidf_cosine(self.documents, other.documents)
        return CorpusComparison(
            corpus_a=self.snapshot(),
            corpus_b=other.snapshot(),
            cosine_similarity=similarity,
            intertextual_distance=1.0 - similarity,
            specificity=specificity,
        )

    def specificity_against(
        self,
        other: CorpusEngine,
        *,
        top_n: int = 50,
    ) -> list[SpecificityResult]:
        total_a = sum(self.term_counts.values())
        total_b = sum(other.term_counts.values())
        if total_a == 0 or total_b == 0:
            return []

        vocabulary = set(self.term_counts) | set(other.term_counts)
        results: list[SpecificityResult] = []

        for term in vocabulary:
            count_a = self.term_counts[term]
            count_b = other.term_counts[term]
            table = np.array(
                [
                    [count_a, total_a - count_a],
                    [count_b, total_b - count_b],
                ],
                dtype=float,
            )
            chi_square = _safe_chi_square(table)
            rate_a = (count_a + 0.5) / (total_a + 1.0)
            rate_b = (count_b + 0.5) / (total_b + 1.0)
            log2_fc = math.log2(rate_a / rate_b)
            direction = "A" if log2_fc > 0 else "B" if log2_fc < 0 else "EVEN"
            results.append(
                SpecificityResult(
                    term=term,
                    count_a=count_a,
                    count_b=count_b,
                    total_a=total_a,
                    total_b=total_b,
                    log2_fold_change_a_over_b=log2_fc,
                    chi_square=chi_square,
                    direction=direction,
                )
            )

        results.sort(
            key=lambda item: (item.chi_square, abs(item.log2_fold_change_a_over_b)),
            reverse=True,
        )
        return results[:top_n]


def _safe_chi_square(table: np.ndarray) -> float:
    if np.any(table < 0):
        return 0.0
    if np.any(table.sum(axis=0) == 0) or np.any(table.sum(axis=1) == 0):
        return 0.0
    try:
        statistic, _, _, _ = chi2_contingency(table, correction=False)
    except ValueError:
        return 0.0
    return float(statistic)


def _corpus_tfidf_cosine(
    documents_a: list[CorpusDocument],
    documents_b: list[CorpusDocument],
) -> float:
    if not documents_a or not documents_b:
        return 0.0

    texts = [document.text for document in documents_a + documents_b]
    vectorizer = TfidfVectorizer(
        tokenizer=tokenize,
        token_pattern=None,
        lowercase=False,
        norm="l2",
    )
    matrix = vectorizer.fit_transform(texts)
    split = len(documents_a)
    centroid_a = np.asarray(matrix[:split].mean(axis=0))
    centroid_b = np.asarray(matrix[split:].mean(axis=0))
    return float(cosine_similarity(centroid_a, centroid_b)[0, 0])
