"""Text encoding detection while preserving the immutable original bytes."""

from __future__ import annotations

from dataclasses import dataclass

from charset_normalizer import from_bytes


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str
    encoding: str
    bom: str | None = None


_BOMS: tuple[tuple[bytes, str, str], ...] = (
    (b"\x00\x00\xfe\xff", "utf-32-be", "UTF-32-BE"),
    (b"\xff\xfe\x00\x00", "utf-32-le", "UTF-32-LE"),
    (b"\xef\xbb\xbf", "utf-8", "UTF-8"),
    (b"\xfe\xff", "utf-16-be", "UTF-16-BE"),
    (b"\xff\xfe", "utf-16-le", "UTF-16-LE"),
)


def decode_text(data: bytes) -> DecodedText:
    for prefix, encoding, label in _BOMS:
        if data.startswith(prefix):
            # Decode with the endian-specific codec so U+FEFF remains observable in the
            # derived RAW_UNICODE view. The immutable bytes remain authoritative.
            return DecodedText(data.decode(encoding, errors="strict"), encoding, label)

    if not data:
        return DecodedText("", "utf-8")

    # Forensic rule: valid UTF-8 is never handed to a heuristic detector. Heuristic
    # misclassification could transform or erase exactly the invisible codepoints that
    # Unicode forensics is meant to inspect.
    try:
        return DecodedText(data.decode("utf-8", errors="strict"), "utf-8")
    except UnicodeDecodeError:
        pass

    match = from_bytes(data).best()
    if match is None or match.encoding is None:
        raise UnicodeError("Unable to determine a safe text encoding")

    return DecodedText(str(match), match.encoding.lower())
