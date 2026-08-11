"""MeshCore NOC beta11 clock tolerance refinement.

Beta10 proved the anonymous BASIC clock read and anti-replay recovery path, but
its companion safety threshold was too strict for a companion that naturally
runs a few seconds fast.  A small positive lead cannot be corrected through the
forward-only companion ``set_time`` API and must not trigger destructive contact
repair when no future ``lastmod`` values exist.

The final repeater sync still requires the repeater to verify within +/-30 s.
"""

from __future__ import annotations

from . import epoch_sync_beta9 as beta9
from . import epoch_sync_beta10 as beta10
from .clock import MeshCoreNocClockManager

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta11_installed"
_COMPANION_SMALL_LEAD_SECONDS = 15


def install_epoch_sync() -> None:
    """Install beta10 and allow a harmless small companion lead."""
    beta10.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    # Companion firmware only permits set_time to move forward.  A small
    # positive offset therefore cannot be corrected normally.  Treat up to
    # 15 seconds as safe; the repeater itself is still verified to +/-30 s by
    # beta10 before a sync can be reported successful.
    beta9._COMPANION_ACCEPTABLE_AHEAD_SECONDS = _COMPANION_SMALL_LEAD_SECONDS

    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


__all__ = ("install_epoch_sync",)
