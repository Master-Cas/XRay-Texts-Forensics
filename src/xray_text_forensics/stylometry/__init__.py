"""Reference-corpus and stylometric comparison."""

from .engine import ReferenceComparator, reference_manifest
from .features import extract_style_fingerprint
from .models import (
    ReferenceComparisonReport,
    ReferenceManifest,
    ReferenceMetadata,
    ReferenceSet,
    ReferenceSimilarity,
    StyleFingerprint,
)

__all__ = [
    "ReferenceComparator",
    "ReferenceComparisonReport",
    "ReferenceManifest",
    "ReferenceMetadata",
    "ReferenceSet",
    "ReferenceSimilarity",
    "StyleFingerprint",
    "extract_style_fingerprint",
    "reference_manifest",
]
