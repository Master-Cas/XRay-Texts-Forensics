# M1 — Forensic Ingestion

## Status

Implementation branch: `m1/forensic-ingestion`

## Objective

Turn arbitrary supported user input into a cryptographically identified **Artifact** before
any parsing, normalization, extraction, or detector execution occurs.

## Scientific rule

**Preserve first. Derive second.**

The immutable original bytes are authoritative evidence. Any decoded, extracted, normalized,
or tokenized representation is a `DerivedView`.

## M1 supported inputs

- TXT
- Markdown
- JSON
- CSV
- HTML
- DOCX and ODT
- PDF

Unknown binary formats are still preservable as artifacts, but do not receive textual views.

## Pipeline

```text
input bytes
    |
size policy
    |
SHA-256 + content-addressed preservation
    |
Artifact
    |
media sniffing
    |
+--- textual source -----------> RAW_UNICODE view
|
+--- safe extractor -----------> EXTRACTED_TEXT view
|
+--- extractor failure --------> warning; Artifact remains valid
```

## Security properties

- input is data, never executable instructions;
- signature sniffing takes precedence over misleading filename extensions;
- input size is bounded;
- DOCX archive entry count and expanded size are bounded;
- PDF page count and extracted text size are bounded;
- original bytes are never normalized in place;
- stored objects are content-addressed and integrity-checked;
- extraction failure does not erase or invalidate preserved evidence.

## Storage

M1 introduces a filesystem content-addressed store:

```text
store/
├── artifacts/<sha-prefix>/<sha256>
└── views/<sha-prefix>/<sha256>
```

This is intentionally independent from the future SQLite/WAL metadata store.

## Derived views

### RAW_UNICODE

Created for textual source formats after encoding detection.

A BOM remains observable where the selected endian-specific codec can preserve it as U+FEFF.

### EXTRACTED_TEXT

Created by a format-specific transformation:

- TXT/Markdown/JSON/CSV: identity text;
- HTML: visible text, excluding script/style/template/noscript contents;
- DOCX: paragraph text from `word/document.xml`;
- PDF: page text through pypdf.

M1 does **not** perform NFC/NFKC normalization. That belongs to Unicode Forensics.

## Gate

M1 is accepted when:

- exact original bytes survive round-trip from the content store;
- SHA-256 identity is stable;
- supported formats create expected views;
- malformed extractable documents preserve their Artifact and produce warnings;
- oversized inputs are rejected before persistence;
- CLI emits machine-readable JSON;
- pytest, Ruff, and mypy pass;
- GitHub CI passes.
