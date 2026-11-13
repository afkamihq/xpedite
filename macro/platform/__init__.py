"""The OS layer: eyes, hands, safety guard and game launch.

Everything above this package uses `open_platform()` and never imports
OS-specific code. Run things from the project root (`python -m ...` or a script
there): putting `macro/` itself on sys.path would make this package shadow the
standard library's `platform`.
"""

from __future__ import annotations

import sys

from .base import GuardTripped, Platform, PointerLocked

PLACE_ID = 84515722934860


def open_platform() -> Platform:
    if sys.platform == "win32":
        from .windows import WindowsPlatform
        return WindowsPlatform()
    from .linux import LinuxPlatform
    return LinuxPlatform()


__all__ = ["GuardTripped", "PLACE_ID", "Platform", "PointerLocked", "open_platform"]
