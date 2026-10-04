"""Known-key watermark detector framework."""

from .base import (
    EnvironmentSecretProvider,
    InMemorySecretProvider,
    SecretProvider,
    StableWordTokenizer,
    WatermarkTokenizer,
)
from .redgreen import (
    RedGreenConfig,
    ReferenceRedGreenDetector,
    generate_reference_watermarked_text,
)

__all__ = [
    "EnvironmentSecretProvider",
    "InMemorySecretProvider",
    "RedGreenConfig",
    "ReferenceRedGreenDetector",
    "SecretProvider",
    "StableWordTokenizer",
    "WatermarkTokenizer",
    "generate_reference_watermarked_text",
]
