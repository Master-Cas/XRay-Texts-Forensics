"""Deterministic Unicode forensic detectors."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from xray_text_forensics.core import (
    Evidence,
    EvidenceFamily,
    EvidenceLocation,
    EvidenceStatus,
)
from xray_text_forensics.detectors.base import (
    AnalysisContext,
    Detector,
    DetectorDescriptor,
    DetectorRequirements,
)


class UnicodeScanPolicy(BaseModel):
    max_locations_per_finding: int = Field(default=500, gt=0)
    suspicious_combining_run: int = Field(default=4, gt=1)


@dataclass(frozen=True, slots=True)
class _FindingSpec:
    finding: str
    predicate: Callable[[str], bool]
    interpretation: str


def _codepoint_label(character: str) -> str:
    code = ord(character)
    name = unicodedata.name(character, "<UNNAMED>")
    return f"U+{code:04X} {name}"


def _is_tag(character: str) -> bool:
    return 0xE0000 <= ord(character) <= 0xE007F


def _is_variation_selector(character: str) -> bool:
    code = ord(character)
    return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF


_ZERO_WIDTH = {
    0x180E,  # MONGOLIAN VOWEL SEPARATOR (historically spacing/format)
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
}

_BIDI = {
    0x061C,
    0x200E,
    0x200F,
    0x202A,
    0x202B,
    0x202C,
    0x202D,
    0x202E,
    0x2066,
    0x2067,
    0x2068,
    0x2069,
}

_SPACE_VARIANTS = {
    0x00A0,
    0x1680,
    *range(0x2000, 0x200B),
    0x202F,
    0x205F,
    0x3000,
}

_STANDARD_CONTROLS = {"\t", "\n", "\r"}

_SPECS: tuple[_FindingSpec, ...] = (
    _FindingSpec(
        "ZERO_WIDTH_CHARACTER",
        lambda c: ord(c) in _ZERO_WIDTH,
        "Exact presence of a zero-width or historically zero-width formatting character.",
    ),
    _FindingSpec(
        "BIDI_CONTROL",
        lambda c: ord(c) in _BIDI,
        "Bidirectional control characters can alter visual ordering without changing logical order.",
    ),
    _FindingSpec(
        "UNICODE_TAG_CHARACTER",
        _is_tag,
        "Unicode tag characters are normally invisible and warrant explicit forensic visibility.",
    ),
    _FindingSpec(
        "VARIATION_SELECTOR",
        _is_variation_selector,
        "Variation selectors modify glyph presentation and may be visually subtle.",
    ),
    _FindingSpec(
        "SPACE_VARIANT",
        lambda c: ord(c) in _SPACE_VARIANTS,
        "Non-ASCII spacing character present; this is descriptive evidence, not proof of manipulation.",
    ),
    _FindingSpec(
        "CONTROL_CHARACTER",
        lambda c: unicodedata.category(c) == "Cc" and c not in _STANDARD_CONTROLS,
        "Non-standard C0/C1 control character present.",
    ),
    _FindingSpec(
        "FORMAT_CONTROL_OTHER",
        lambda c: unicodedata.category(c) == "Cf"
        and ord(c) not in _ZERO_WIDTH
        and ord(c) not in _BIDI
        and not _is_tag(c),
        "Other Unicode format-control character present.",
    ),
)


class UnicodeCodepointDetector(Detector):
    def __init__(self, policy: UnicodeScanPolicy | None = None) -> None:
        self.policy = policy or UnicodeScanPolicy()

    @property
    def descriptor(self) -> DetectorDescriptor:
        return DetectorDescriptor(
            detector_id="unicode.codepoints",
            version="1.0.0",
            family=EvidenceFamily.UNICODE,
            requirements=DetectorRequirements(raw_unicode=True),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        selected = context.preferred_text_view()
        if selected is None:
            return [
                Evidence(
                    artifact_id=context.artifact.artifact_id,
                    family=EvidenceFamily.UNICODE,
                    status=EvidenceStatus.NOT_TESTABLE,
                    detector_id=self.descriptor.detector_id,
                    detector_version=self.descriptor.version,
                    finding="UNICODE_CODEPOINT_SCAN",
                    reason="No RAW_UNICODE or EXTRACTED_TEXT view is available.",
                )
            ]

        view, text = selected
        evidence = [self._scan_spec(context, view.view_id, text, spec) for spec in _SPECS]
        evidence.append(self._scan_combining(context, view.view_id, text))
        return evidence

    def _scan_spec(
        self,
        context: AnalysisContext,
        view_id: str,
        text: str,
        spec: _FindingSpec,
    ) -> Evidence:
        matches = [(index, char) for index, char in enumerate(text) if spec.predicate(char)]
        locations = [
            EvidenceLocation(start=index, end=index + 1, label=_codepoint_label(char))
            for index, char in matches[: self.policy.max_locations_per_finding]
        ]
        return Evidence(
            artifact_id=context.artifact.artifact_id,
            family=EvidenceFamily.UNICODE,
            status=EvidenceStatus.DETECTED if matches else EvidenceStatus.NOT_DETECTED,
            detector_id=self.descriptor.detector_id,
            detector_version=self.descriptor.version,
            finding=spec.finding,
            confidence=1.0,
            derived_view_id=view_id,
            locations=locations,
            parameters={
                "total_count": len(matches),
                "locations_truncated": len(matches) > len(locations),
                "interpretation": spec.interpretation,
            },
        )

    def _scan_combining(
        self,
        context: AnalysisContext,
        view_id: str,
        text: str,
    ) -> Evidence:
        locations: list[EvidenceLocation] = []
        total = 0
        index = 0

        while index < len(text):
            if not unicodedata.category(text[index]).startswith("M"):
                index += 1
                continue

            start = index
            while index < len(text) and unicodedata.category(text[index]).startswith("M"):
                index += 1
            run_length = index - start
            isolated = start == 0 or text[start - 1].isspace()

            if isolated or run_length >= self.policy.suspicious_combining_run:
                total += 1
                if len(locations) < self.policy.max_locations_per_finding:
                    labels = ", ".join(_codepoint_label(char) for char in text[start:index])
                    locations.append(
                        EvidenceLocation(
                            start=start,
                            end=index,
                            label=f"{run_length} combining mark(s): {labels}",
                        )
                    )

        return Evidence(
            artifact_id=context.artifact.artifact_id,
            family=EvidenceFamily.UNICODE,
            status=EvidenceStatus.DETECTED if total else EvidenceStatus.NOT_DETECTED,
            detector_id=self.descriptor.detector_id,
            detector_version=self.descriptor.version,
            finding="SUSPICIOUS_COMBINING_SEQUENCE",
            confidence=1.0,
            derived_view_id=view_id,
            locations=locations,
            parameters={
                "total_sequences": total,
                "locations_truncated": total > len(locations),
                "threshold": self.policy.suspicious_combining_run,
                "interpretation": (
                    "Flags isolated combining marks or unusually long consecutive combining runs; "
                    "ordinary composed/decomposed accents are not automatically suspicious."
                ),
            },
        )


class UnicodeNormalizationDetector(Detector):
    @property
    def descriptor(self) -> DetectorDescriptor:
        return DetectorDescriptor(
            detector_id="unicode.normalization",
            version="1.0.0",
            family=EvidenceFamily.UNICODE,
            requirements=DetectorRequirements(raw_unicode=True),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        selected = context.preferred_text_view()
        if selected is None:
            return [
                Evidence(
                    artifact_id=context.artifact.artifact_id,
                    family=EvidenceFamily.UNICODE,
                    status=EvidenceStatus.NOT_TESTABLE,
                    detector_id=self.descriptor.detector_id,
                    detector_version=self.descriptor.version,
                    finding="NORMALIZATION_DIFFERENCE",
                    reason="No RAW_UNICODE or EXTRACTED_TEXT view is available.",
                )
            ]

        view, text = selected
        forms: dict[str, dict[str, str | int | bool]] = {}
        any_changed = False

        for form in ("NFC", "NFD", "NFKC", "NFKD"):
            normalized = unicodedata.normalize(form, text)
            changed = normalized != text
            any_changed = any_changed or changed
            forms[form] = {
                "changed": changed,
                "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                "char_length": len(normalized),
            }

        return [
            Evidence(
                artifact_id=context.artifact.artifact_id,
                family=EvidenceFamily.UNICODE,
                status=EvidenceStatus.DETECTED if any_changed else EvidenceStatus.NOT_DETECTED,
                detector_id=self.descriptor.detector_id,
                detector_version=self.descriptor.version,
                finding="NORMALIZATION_DIFFERENCE",
                confidence=1.0,
                derived_view_id=view.view_id,
                parameters={
                    "forms": forms,
                    "interpretation": (
                        "A normalization difference is deterministic descriptive evidence. "
                        "It is not by itself proof of watermarking or manipulation."
                    ),
                },
            )
        ]


_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _script(character: str) -> str | None:
    name = unicodedata.name(character, "")
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if script in name:
            return script
    return None


class MixedScriptDetector(Detector):
    def __init__(self, policy: UnicodeScanPolicy | None = None) -> None:
        self.policy = policy or UnicodeScanPolicy()

    @property
    def descriptor(self) -> DetectorDescriptor:
        return DetectorDescriptor(
            detector_id="unicode.mixed_script",
            version="1.0.0",
            family=EvidenceFamily.UNICODE,
            requirements=DetectorRequirements(raw_unicode=True),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        selected = context.preferred_text_view()
        if selected is None:
            return [
                Evidence(
                    artifact_id=context.artifact.artifact_id,
                    family=EvidenceFamily.UNICODE,
                    status=EvidenceStatus.NOT_TESTABLE,
                    detector_id=self.descriptor.detector_id,
                    detector_version=self.descriptor.version,
                    finding="MIXED_SCRIPT_TOKEN",
                    reason="No RAW_UNICODE or EXTRACTED_TEXT view is available.",
                )
            ]

        view, text = selected
        locations: list[EvidenceLocation] = []
        total = 0
        examples: list[str] = []

        for match in _WORD_RE.finditer(text):
            token = match.group(0)
            scripts = {script for char in token if (script := _script(char)) is not None}
            if len(scripts) <= 1:
                continue

            total += 1
            if len(examples) < 20:
                examples.append(token)
            if len(locations) < self.policy.max_locations_per_finding:
                locations.append(
                    EvidenceLocation(
                        start=match.start(),
                        end=match.end(),
                        label=f"{token!r}: {', '.join(sorted(scripts))}",
                    )
                )

        return [
            Evidence(
                artifact_id=context.artifact.artifact_id,
                family=EvidenceFamily.UNICODE,
                status=EvidenceStatus.DETECTED if total else EvidenceStatus.NOT_DETECTED,
                detector_id=self.descriptor.detector_id,
                detector_version=self.descriptor.version,
                finding="MIXED_SCRIPT_TOKEN",
                derived_view_id=view.view_id,
                locations=locations,
                parameters={
                    "total_count": total,
                    "locations_truncated": total > len(locations),
                    "examples": examples,
                    "scripts_checked": ["LATIN", "CYRILLIC", "GREEK"],
                    "interpretation": (
                        "Mixed-script tokens may indicate homoglyph substitution, but can also be "
                        "legitimate. This heuristic is not authorship or intent evidence."
                    ),
                },
            )
        ]


class UnicodeForensicsSuite:
    def __init__(self, policy: UnicodeScanPolicy | None = None) -> None:
        policy = policy or UnicodeScanPolicy()
        self.detectors: tuple[Detector, ...] = (
            UnicodeCodepointDetector(policy),
            UnicodeNormalizationDetector(),
            MixedScriptDetector(policy),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        evidence: list[Evidence] = []
        for detector in self.detectors:
            evidence.extend(detector.analyze(context))
        return evidence
