"""
Helper to resolve resource paths both in development and in a
PyInstaller-built one-file/one-folder executable.

When running from a PyInstaller bundle, data files are unpacked to a
temporary folder available as sys._MEIPASS. In development we fall back
to the directory of this file.
"""

import os
import sys


def resource_path(relative_path: str) -> str:
    """Return absolute path to a bundled resource."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is None:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)
