"""MeshCore NOC beta12 companion tolerance and clock-check clarity.

Beta10 proved that anonymous BASIC clock reads bypass stale administrator replay
state and that the anti-replay recovery clkreboot can reset a stranded repeater.
Beta11 accepted a small positive companion lead, but field testing showed the
ProMicro companion can naturally be around +17 seconds ahead. Because the
companion firmware only permits ``set_time`` to move forward, a small positive
lead cannot be corrected directly and must not trigger contact-table repair.

Beta12 therefore accepts a companion lead up to the same +/-30 second window
used for final repeater sync verification. Anonymous BASIC timeouts are also
reported as reachability/radio-path failures instead of sounding like a clock
parser failure.
"""

from __future__ import annotations

from . import epoch_sync_beta9 as beta9
from . import epoch_sync_beta10 as beta10
from . import epoch_sync_beta11 as beta11
from .clock import ClockCheckState, MeshCoreNocClockManager

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta12_installed"
_COMPANION_SAFE_LEAD_SECONDS = 30
_ORIGINAL_ANON_CHECK = beta10._async_check_clock_anon


async def _async_check_clock_with_reachability_message(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
):
    """Run the anonymous clock read and clarify genuine no-response failures."""
    result = await _ORIGINAL_ANON_CHECK(
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
        result.error = (
            "No anonymous clock response received — repeater may be offline, "
            "unreachable, or have a stale radio path."
        )
        result.last_clock_attempt_error = result.error
        self._notify(result.stable_id)
    return result


def install_epoch_sync() -> None:
    """Install beta11, then apply the field-tested beta12 refinements."""
    beta11.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    # Keep the companion safety gate aligned with the final repeater
    # verification window. A lead within 30 seconds is safe to use as a clock
    # source and cannot be corrected backwards through the companion API.
    beta9._COMPANION_ACCEPTABLE_AHEAD_SECONDS = _COMPANION_SAFE_LEAD_SECONDS

    MeshCoreNocClockManager.async_check_clock = (
        _async_check_clock_with_reachability_message
    )

    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


__all__ = ("install_epoch_sync",)
