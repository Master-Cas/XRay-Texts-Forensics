# M2 — Unicode Forensics

## Objective

Expose hidden or visually deceptive Unicode characteristics without silently normalizing
the source or pretending that their presence proves watermarking, AI authorship, or intent.

## Input preference

```text
RAW_UNICODE
    |
    +-- preferred when original source is textual

EXTRACTED_TEXT
    |
    +-- fallback for PDF/DOCX and other container formats
```

Every Evidence record states the exact `derived_view_id` that was scanned.

## Deterministic codepoint findings

M2 scans for:

- zero-width characters;
- bidi controls;
- Unicode tag characters;
- variation selectors;
- non-ASCII space variants;
- non-standard C0/C1 controls;
- other Unicode format controls;
- suspicious combining-mark sequences.

Exact character offsets and Unicode names are recorded, subject to a bounded location count.

## Mixed-script heuristic

Tokens mixing Latin, Cyrillic, and/or Greek characters are surfaced because homoglyph
substitution often crosses those scripts.

This is a heuristic and is explicitly **not** treated as proof of deception or authorship.

## Normalization forensics

M2 compares the selected text view with:

- NFC
- NFD
- NFKC
- NFKD

It records whether each form changes the text plus the normalized SHA-256 and character
length.

M2 does **not** replace the original or selected view with normalized text.

## Interpretation rule

```text
character present
      !=
malicious manipulation
      !=
watermark
      !=
AI authorship
```

A deterministic `DETECTED` status means the defined Unicode feature is present.

## CLI

```bash
xray unicode document.txt
xray unicode document.txt --json
```

## Gate

M2 is accepted when:

- hidden-character classes are detected at exact offsets;
- normal text produces negative results for those classes;
- NFKC/NFC differences are deterministic and traceable;
- mixed-script tokens are surfaced without claiming authorship;
- ordinary single combining accents are not mislabeled as suspicious runs;
- CLI JSON is stable;
- pytest, Ruff, and mypy pass;
- GitHub CI passes.
