"""XRay web backend."""

from .app import create_app
from .settings import WebSettings

__all__ = ["WebSettings", "create_app"]
