"""Desktop launcher for XRay."""

from .app import main
from .server import DesktopServer, default_desktop_data_root

__all__ = ["DesktopServer", "default_desktop_data_root", "main"]
