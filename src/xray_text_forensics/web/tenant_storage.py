"""Tenant-scoped storage paths.

Raw tenant identifiers are never used as filesystem path components. A stable digest maps
each authenticated tenant to an opaque directory.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .identity import Principal


@dataclass(frozen=True, slots=True)
class TenantStorage:
    tenant_id: str
    root: Path

    @property
    def object_store_root(self) -> Path:
        return self.root / "objects"

    @property
    def case_database(self) -> Path:
        return self.root / "cases.sqlite"

    @property
    def reference_root(self) -> Path:
        return self.root / "references"

    @property
    def reference_object_store_root(self) -> Path:
        return self.root / "reference-objects"


class TenantStorageResolver:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def for_principal(self, principal: Principal) -> TenantStorage:
        if principal.tenant_id == "local":
            root = self.data_root
        else:
            digest = hashlib.sha256(principal.tenant_id.encode("utf-8")).hexdigest()
            root = self.data_root / "tenants" / digest[:32]

        root.mkdir(parents=True, exist_ok=True)
        (root / "objects").mkdir(parents=True, exist_ok=True)
        (root / "references").mkdir(parents=True, exist_ok=True)
        (root / "reference-objects").mkdir(parents=True, exist_ok=True)
        return TenantStorage(
            tenant_id=principal.tenant_id,
            root=root,
        )
