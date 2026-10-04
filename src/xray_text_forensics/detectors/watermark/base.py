"""Common contracts for known-key watermark detection."""

from __future__ import annotations

import hashlib
import os
from typing import Protocol

from xray_text_forensics.corpus.tokenize import tokenize


class SecretProvider(Protocol):
    """Resolve secret material without exposing it to detector output."""

    def get_secret(self, reference: str) -> bytes | None: ...


class WatermarkTokenizer(Protocol):
    """Map text to the exact token IDs required by a detector."""

    @property
    def tokenizer_id(self) -> str: ...

    def encode(self, text: str) -> list[int]: ...


class EnvironmentSecretProvider:
    def get_secret(self, reference: str) -> bytes | None:
        value = os.environ.get(reference)
        return value.encode("utf-8") if value is not None else None


class InMemorySecretProvider:
    """Test/development provider. Never serialize its values."""

    def __init__(self, secrets: dict[str, bytes]) -> None:
        self._secrets = dict(secrets)

    def get_secret(self, reference: str) -> bytes | None:
        return self._secrets.get(reference)


class StableWordTokenizer:
    """Deterministic reference tokenizer for XRay test watermarking.

    This is deliberately not a provider/model tokenizer and therefore must not be used to
    claim compatibility with SynthID or another production watermark.
    """

    @property
    def tokenizer_id(self) -> str:
        return "xray.stable-word-sha256.v1"

    def encode(self, text: str) -> list[int]:
        return [self.token_id(token) for token in tokenize(text)]

    @staticmethod
    def token_id(token: str) -> int:
        digest = hashlib.sha256(token.casefold().encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big", signed=False)
