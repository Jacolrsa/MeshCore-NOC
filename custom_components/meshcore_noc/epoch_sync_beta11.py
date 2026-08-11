"""MeshCore NOC beta11 clock tolerance refinement.

Beta10 proved the anonymous BASIC clock read and anti-replay recovery path, but
its companion safety threshold was too strict for a companion that naturally
runs a few seconds fast. A small positive lead cannot be corrected through the
forward-only companion ``set_time`` API and must not trigger contact repair when
no future ``lastmod`` values exist.

Anonymous BASIC checks are retained. If a repeater does not answer, the UI now
makes clear that this is a radio/reachability result rather than a login or clock
protocol failure.

The final repeater sync still requires the repeater to verify within +/-30 s.
"""

from __future__ import annotations

from typing import Any

from . import epoch_sync_beta9 as beta9
from . import epoch_sync_beta10 as beta10
from .clock import ClockCheckState, MeshCoreNocClockManager

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta11_installed"
_COMPANION_SMALL_LEAD_SECONDS = 15


def install_epoch_sync() -> None:
    """Install beta10, tolerate a small lead, and clarify radio timeouts."""
    beta10.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    # Companion firmware only permits set_time to move forward. A small
    # positive offset therefore cannot be corrected normally. Treat up to
    # 15 seconds as safe; the repeater itself is still verified to +/-30 s by
    # beta10 before a sync can be reported successful.
    beta9._COMPANION_ACCEPTABLE_AHEAD_SECONDS = _COMPANION_SMALL_LEAD_SECONDS

    MeshCoreNocClockManager.async_check_clock = _async_check_clock_with_clear_timeout
    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


async def _async_check_clock_with_clear_timeout(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
) -> Any:
    """Use beta10 anonymous clock reads with a meaningful no-radio-response error."""
    result = await beta10._async_check_clock_anon(
        self,
        stable_id,
        fleet_run_id=fleet_run_id,
        sync_operation=sync_operation,
        bypass_cooldown=bypass_cooldown,
    )
    if (
        result.state is ClockCheckState.TIMED_OUT
        and result.error == "anonymous clock response timed out"
    ):
        message = (
            "No clock response received; repeater may be offline, unreachable, "
            "or have a stale radio path."
        )
        result.error = message
        result.last_clock_attempt_error = message
        self._notify(result.stable_id)
    return result


__all__ = ("install_epoch_sync",)
