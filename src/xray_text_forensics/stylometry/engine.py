"""Reference-corpus profiler with separated style/content signals."""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

from xray_text_forensics.corpus.tokenize import tokenize

from .features import extract_style_fingerprint, fingerprint_vector
from .models import (
    ReferenceComparisonReport,
    ReferenceManifest,
    ReferenceSet,
    ReferenceSimilarity,
)


def reference_manifest(reference: ReferenceSet) -> ReferenceManifest:
    payload = {
        "metadata": reference.metadata.model_dump(mode="json"),
        "documents": [
            {
                "document_id": document.document_id,
                "sha256": hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
                "metadata": document.metadata,
            }
            for document in sorted(reference.documents, key=lambda item: item.document_id)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    metadata = reference.metadata
    return ReferenceManifest(
        label=metadata.label,
        document_count=len(reference.documents),
        manifest_sha256=digest,
        provider=metadata.provider,
        model=metadata.model,
        model_version=metadata.model_version,
        language=metadata.language,
        topic=metadata.topic,
        source=metadata.source,
        license=metadata.license,
    )


class ReferenceComparator:
    """Fit reference corpora once and compare suspect texts in separate feature spaces."""

    def __init__(self, references: list[ReferenceSet]) -> None:
        if not references:
            raise ValueError("At least one reference set is required")
        if any(not reference.documents for reference in references):
            raise ValueError("Reference sets must contain at least one document")

        self.references = references
        self.manifests = {
            reference.metadata.label: reference_manifest(reference) for reference in references
        }

        labels: list[str] = []
        texts: list[str] = []
        style_vectors: list[list[float]] = []
        for reference in references:
            for document in reference.documents:
                labels.append(reference.metadata.label)
                texts.append(document.text)
                style_vectors.append(
                    fingerprint_vector(extract_style_fingerprint(document.text))
                )

        self._labels = labels
        self._style_scaler = StandardScaler()
        self._style_matrix = self._style_scaler.fit_transform(
            np.asarray(style_vectors, dtype=float)
        )

        self._char_vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            min_df=1,
            max_features=5000,
            norm="l2",
        )
        char_matrix = self._char_vectorizer.fit_transform(texts)
        n_components = min(16, char_matrix.shape[0] - 1, char_matrix.shape[1] - 1)
        self._char_svd: TruncatedSVD | None
        if n_components >= 2:
            self._char_svd = TruncatedSVD(n_components=n_components, random_state=0)
            self._char_matrix = self._char_svd.fit_transform(char_matrix)
        else:
            self._char_svd = None
            self._char_matrix = char_matrix.toarray()

        self._content_vectorizer = TfidfVectorizer(
            tokenizer=tokenize,
            token_pattern=None,
            lowercase=False,
            norm="l2",
        )
        self._content_matrix = self._content_vectorizer.fit_transform(texts).toarray()

        self._style_centroids = self._centroids(self._style_matrix)
        self._char_centroids = self._centroids(self._char_matrix)
        self._content_centroids = self._centroids(self._content_matrix)

    def compare(self, text: str) -> ReferenceComparisonReport:
        suspect_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        style = np.asarray(
            [fingerprint_vector(extract_style_fingerprint(text))],
            dtype=float,
        )
        style_vector = self._style_scaler.transform(style)[0]

        char_raw = self._char_vectorizer.transform([text])
        char_vector = (
            self._char_svd.transform(char_raw)[0]
            if self._char_svd is not None
            else char_raw.toarray()[0]
        )
        content_vector = self._content_vectorizer.transform([text]).toarray()[0]

        comparisons: list[ReferenceSimilarity] = []
        for label in sorted(self.manifests):
            manifest = self.manifests[label]
            style_distance = float(
                np.linalg.norm(style_vector - self._style_centroids[label])
            )
            style_similarity = 1.0 / (1.0 + style_distance)
            char_similarity = _cosine(char_vector, self._char_centroids[label])
            content_similarity = _cosine(content_vector, self._content_centroids[label])

            comparisons.append(
                ReferenceSimilarity(
                    label=label,
                    manifest_sha256=manifest.manifest_sha256,
                    document_count=manifest.document_count,
                    style_similarity=style_similarity,
                    char_svd_similarity=char_similarity,
                    content_similarity=content_similarity,
                    interpretation=(
                        "Similarity to this versioned reference corpus. Style, "
                        "character-SVD, and content signals are intentionally not fused "
                        "into authorship."
                    ),
                )
            )

        return ReferenceComparisonReport(
            suspect_sha256=suspect_sha,
            comparisons=comparisons,
        )

    def _centroids(self, matrix: np.ndarray) -> dict[str, np.ndarray]:
        centroids: dict[str, np.ndarray] = {}
        labels_array = np.asarray(self._labels)
        for label in sorted(set(self._labels)):
            centroids[label] = np.asarray(matrix[labels_array == label].mean(axis=0))
        return centroids


def _cosine(first: np.ndarray, second: np.ndarray) -> float:
    if math.isclose(float(np.linalg.norm(first)), 0.0) or math.isclose(
        float(np.linalg.norm(second)),
        0.0,
    ):
        return 0.0
    return float(cosine_similarity(first.reshape(1, -1), second.reshape(1, -1))[0, 0])
