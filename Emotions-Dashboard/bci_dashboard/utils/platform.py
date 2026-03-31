"""Cross-platform helpers for OS-specific operations."""
from __future__ import annotations

import os
import subprocess
import sys


def open_folder(path: str) -> None:
    """Open a folder in the system file manager (cross-platform)."""
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def native_lib_name(base: str) -> str:
    """Return the platform-appropriate shared library filename.

    >>> native_lib_name("CapsuleClient")  # Windows → 'CapsuleClient.dll'
    >>> native_lib_name("CapsuleClient")  # macOS   → 'libCapsuleClient.dylib'
    >>> native_lib_name("CapsuleClient")  # Linux   → 'libCapsuleClient.so'
    """
    if sys.platform == "win32":
        return f"{base}.dll"
    if sys.platform == "darwin":
        return f"lib{base}.dylib"
    return f"lib{base}.so"
