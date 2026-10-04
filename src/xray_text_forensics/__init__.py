"""XRay Texts Forensics core package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xray-texts-forensics")
except PackageNotFoundError:
    __version__ = "0.0.0+uninstalled"

__all__ = ["__version__"]
