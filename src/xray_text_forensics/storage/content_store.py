"""Filesystem-backed content-addressed storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredObject:
    sha256: str
    byte_length: int
    path: Path

    @property
    def uri(self) -> str:
        return self.path.resolve().as_uri()


class ContentAddressedStore:
    """Store bytes by digest without allowing content replacement.

    Immutability is enforced at the application layer: an existing digest path is verified
    and never overwritten with caller-provided content.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, namespace: str, sha256: str) -> Path:
        return self.root / namespace / sha256[:2] / sha256

    def put_bytes(self, namespace: str, data: bytes) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        destination = self._object_path(namespace, digest)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            self._verify_existing(destination, digest, len(data))
            return StoredObject(digest, len(data), destination)

        fd, temporary_name = tempfile.mkstemp(prefix=".xray-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())

            if destination.exists():
                self._verify_existing(destination, digest, len(data))
            else:
                os.replace(temporary, destination)

            self._verify_existing(destination, digest, len(data))
            return StoredObject(digest, len(data), destination)
        finally:
            temporary.unlink(missing_ok=True)

    def read_bytes(self, stored: StoredObject) -> bytes:
        data = stored.path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != stored.sha256 or len(data) != stored.byte_length:
            raise OSError(f"Stored object integrity failure: {stored.path}")
        return data

    @staticmethod
    def _verify_existing(path: Path, expected_sha256: str, expected_size: int) -> None:
        stat = path.stat()
        if stat.st_size != expected_size:
            raise OSError(f"Content-addressed object has unexpected size: {path}")

        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)

        if hasher.hexdigest() != expected_sha256:
            raise OSError(f"Content-addressed object has unexpected digest: {path}")
