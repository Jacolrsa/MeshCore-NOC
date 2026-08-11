"""MeshCore NOC beta15 latency-aware clocks and safer automation.

Beta15 builds on beta14's route-aware authenticated clock operations.  It adds
three production hardening changes:

* Clock offsets are compensated by half of the measured authenticated clock
  command round-trip time, so radio travel time is not reported as RTC drift.
* ``clock sync`` is transmitted with an explicit latency-compensated timestamp
  chosen above the connected companion clock to preserve repeater anti-replay
  ordering.  Repeaters already within +/-30 seconds are left untouched.
* Obsolete clock cooldown/fleet pacing controls are hidden from the options UI;
  stored values remain readable for rollback compatibility.  Automatic sync is
  prevented from starting when any managed repeater lacks a saved administrator
  password.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import replace
from typing import Any

import voluptuous as vol
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from . import config_flow as config_flow_module
from . import epoch_sync_beta8 as beta8
from . import epoch_sync_beta9 as beta9
from . import epoch_sync_beta14 as beta14
from .clock import (
    ClockCheckState,
    ClockSyncResult,
    ClockSyncState,
    MeshCoreNocClockManager,
    classify_clock_status,
)
from .const import (
    CONF_AUTO_FLEET_CLOCK_CHECKS,
    CONF_AUTO_FLEET_CLOCK_SYNC,
    CONF_FLEET_CLOCK_INTERVAL_HOURS,
    CONF_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
    CONF_MANAGED_REPEATER_IDS,
    CONF_UPDATE_CHANNEL,
    DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    DEFAULT_AUTO_FLEET_CLOCK_SYNC,
    DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    DEFAULT_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
    DEFAULT_UPDATE_CHANNEL,
    FLEET_CLOCK_SYNC_INTERVAL_OPTIONS,
    MAX_FLEET_CLOCK_INTERVAL_HOURS,
    MIN_FLEET_CLOCK_INTERVAL_HOURS,
    UPDATE_CHANNEL_DEVELOPMENT,
    UPDATE_CHANNEL_STABLE,
)
from .fleet_sync import (
    FleetClockSyncOrchestrator,
    FleetClockSyncState,
    FleetClockSyncTrigger,
)

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta15_installed"
_SYNC_TOLERANCE_SECONDS = 30
_MAX_LATENCY_COMPENSATION_SECONDS = 30
_CLOCK_COMMAND_RE = re.compile(r"^\s*send_cmd\([^,]+,\s*[\"']clock[\"']\s*\)\s*$")

_PREVIOUS_RAW_HANDLER = None
_PREVIOUS_EXECUTE_COMMAND = None
_PREVIOUS_SYNC = None
_PREVIOUS_REMOTE_COMMAND = None
_PREVIOUS_AUTO_SYNC_START = None


def _clock_probes(manager: MeshCoreNocClockManager) -> dict[str, dict[str, Any]]:
    return manager.__dict__.setdefault("_beta15_clock_probes", {})


def _clean_selection_schema(
    repeaters,
    selected,
    update_channel: str = DEFAULT_UPDATE_CHANNEL,
    clock_check_cooldown: int = 0,
    auto_fleet_clock_checks: bool = DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    fleet_clock_interval_hours: int = DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    fleet_success_delay: int = 0,
    fleet_failure_delay: int = 0,
    fleet_rotating_start: bool = False,
    auto_fleet_clock_sync: bool = DEFAULT_AUTO_FLEET_CLOCK_SYNC,
    fleet_clock_sync_interval_hours: int = DEFAULT_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
) -> vol.Schema:
    """Return only operator controls that still affect runtime behaviour.

    Legacy arguments intentionally remain in the signature because the existing
    config/options flow still passes them. They are not shown and their stored
    values are preserved by the flow's merge logic.
    """
    del clock_check_cooldown, fleet_success_delay, fleet_failure_delay, fleet_rotating_start

    options = config_flow_module._selection_options(repeaters)
    available_ids = set(repeaters)
    default = [stable_id for stable_id in selected if stable_id in available_ids]
    return vol.Schema(
        {
            vol.Required(CONF_MANAGED_REPEATER_IDS, default=default): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True)
            ),
            vol.Required(
                CONF_AUTO_FLEET_CLOCK_CHECKS, default=auto_fleet_clock_checks
            ): BooleanSelector(),
            vol.Required(
                CONF_FLEET_CLOCK_INTERVAL_HOURS,
                default=fleet_clock_interval_hours,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_FLEET_CLOCK_INTERVAL_HOURS,
                    max=MAX_FLEET_CLOCK_INTERVAL_HOURS,
                    step=1,
                    unit_of_measurement="hours",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_AUTO_FLEET_CLOCK_SYNC, default=auto_fleet_clock_sync
            ): BooleanSelector(),
            vol.Required(
                CONF_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
                default=str(fleet_clock_sync_interval_hours),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {
                            "value": str(hours),
                            "label": (
                                f"{hours} hours"
                                if hours < 24
                                else (
                                    "24 hours"
                                    if hours == 24
                                    else f"{hours // 24} days"
                                )
                            ),
                        }
                        for hours in FLEET_CLOCK_SYNC_INTERVAL_OPTIONS
                    ],
                    multiple=False,
                )
            ),
            vol.Required(CONF_UPDATE_CHANNEL, default=update_channel): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": UPDATE_CHANNEL_STABLE, "label": "Stable"},
                        {
                            "value": UPDATE_CHANNEL_DEVELOPMENT,
                            "label": "Development",
                        },
                    ],
                    multiple=False,
                )
            ),
        }
    )


async def _execute_meshcore_command_with_probe(
    manager: MeshCoreNocClockManager,
    target: Any,
    command: str,
) -> dict[str, Any]:
    """Timestamp authenticated ``clock`` transmissions at the service boundary."""
    assert _PREVIOUS_EXECUTE_COMMAND is not None
    if _CLOCK_COMMAND_RE.fullmatch(command):
        _clock_probes(manager)[target.pubkey_prefix.lower()] = {
            "sent_monotonic": manager._monotonic(),
            "sent_at": manager._utc_now(),
        }
    return await _PREVIOUS_EXECUTE_COMMAND(manager, target, command)


def _apply_latency_compensation(
    manager: MeshCoreNocClockManager,
    prefix: str,
    received_monotonic: float,
) -> None:
    probes = _clock_probes(manager)
    probe = probes.get(prefix)
    if not probe:
        return
    target = next(
        (item for item in manager.targets.values() if item.pubkey_prefix.lower() == prefix),
        None,
    )
    if target is None:
        return
    result = manager.result_for(target.stable_id)
    if result is None or result.state is not ClockCheckState.COMPLETED:
        return
    probes.pop(prefix, None)

    try:
        rtt_seconds = max(0.0, received_monotonic - float(probe["sent_monotonic"]))
    except (KeyError, TypeError, ValueError):
        return

    raw_offset = result.clock_offset_seconds
    if raw_offset is None:
        return
    compensation = min(rtt_seconds / 2.0, float(_MAX_LATENCY_COMPENSATION_SECONDS))
    corrected_offset = round(float(raw_offset) + compensation)
    result.clock_rtt_ms = round(rtt_seconds * 1000)
    result.clock_offset_seconds = corrected_offset
    warning, critical = (
        manager._clock_thresholds(result.stable_id)
        if manager._clock_thresholds is not None
        else (120, 300)
    )
    result.clock_status = classify_clock_status(corrected_offset, warning, critical)

    manager.last_parse_result = {
        **(manager.last_parse_result or {}),
        "raw_clock_offset_seconds": raw_offset,
        "latency_compensation_seconds": round(compensation, 3),
        "clock_rtt_ms": result.clock_rtt_ms,
        "clock_offset_seconds": corrected_offset,
    }
    if manager.last_response is not None:
        manager.last_response = {
            **manager.last_response,
            "clock_rtt_ms": result.clock_rtt_ms,
            "raw_clock_offset_seconds": raw_offset,
            "latency_compensation_seconds": round(compensation, 3),
            "clock_offset_seconds": corrected_offset,
        }

    if manager._history:
        latest = manager._history[-1]
        if latest.stable_id == result.stable_id and latest.state is ClockCheckState.COMPLETED:
            manager._history[-1] = replace(
                latest,
                clock_offset_seconds=corrected_offset,
                clock_status=result.clock_status,
                clock_rtt_ms=result.clock_rtt_ms,
            )
    manager._notify(result.stable_id)


@callback
def _async_handle_raw_event_latency_aware(self: MeshCoreNocClockManager, event: Any) -> None:
    """Let beta14 finish correlation, then correct completed clock samples."""
    assert _PREVIOUS_RAW_HANDLER is not None
    received_monotonic = self._monotonic()
    data = getattr(event, "data", {})
    payload = data.get("payload") if isinstance(data, dict) else None
    prefix = (
        str(payload.get("pubkey_prefix", "")).lower()
        if isinstance(payload, dict)
        else ""
    )
    _PREVIOUS_RAW_HANDLER(self, event)
    if prefix:
        _apply_latency_compensation(self, prefix, received_monotonic)


async def _send_remote_command_latency_aware(
    manager: MeshCoreNocClockManager,
    target: Any,
    remote_command: str,
    *,
    reply_timeout: float | None = None,
) -> str | None:
    """Compensate only ``clock sync``; delegate every other CLI command."""
    assert _PREVIOUS_REMOTE_COMMAND is not None
    if remote_command != "clock sync":
        return await _PREVIOUS_REMOTE_COMMAND(
            manager,
            target,
            remote_command,
            reply_timeout=reply_timeout,
        )

    result = manager.result_for(target.stable_id)
    rtt_ms = result.clock_rtt_ms if result is not None else None
    one_way = min(
        max(float(rtt_ms or 0) / 2000.0, 0.0),
        float(_MAX_LATENCY_COMPENSATION_SECONDS),
    )
    try:
        companion_epoch, _companion_offset = await beta9._verify_companion(
            manager, target
        )
    except Exception:  # noqa: BLE001 - fallback remains safe and forward-only
        companion_epoch = int(manager._utc_now().timestamp())

    ha_epoch = int(manager._utc_now().timestamp())
    sender_epoch = max(
        int(companion_epoch) + 1,
        ha_epoch + max(1, math.ceil(one_way)),
    )
    beta8._append_sync_line(
        manager,
        target.stable_id,
        (
            f"Latency compensation: clock RTT {float(rtt_ms or 0) / 1000.0:.1f} s; "
            f"using +{max(1, math.ceil(one_way))} s one-way estimate for clock sync."
        ),
    )

    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[str] | None = None
    pending = beta8._pending_remote_replies(manager)
    if reply_timeout is not None:
        future = asyncio.get_running_loop().create_future()
        pending[prefix] = future
    command = (
        f"send_cmd({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(remote_command)}, timestamp={sender_epoch})"
    )
    try:
        response = await beta8._execute_meshcore_command(manager, target, command)
        if future is None:
            return None
        wait_seconds = beta14._route_wait_seconds(
            response,
            fallback_seconds=float(reply_timeout),
            minimum_seconds=max(beta14._MIN_ROUTE_WAIT_SECONDS, float(reply_timeout)),
        )
        beta14._route_timing(manager)[prefix] = {
            "operation": "remote:clock sync",
            "suggested_timeout": response.get("suggested_timeout"),
            "wait_seconds": wait_seconds,
            "latency_compensated_sender_epoch": sender_epoch,
            "one_way_estimate_seconds": one_way,
        }
        if future.done():
            return future.result()
        try:
            async with asyncio.timeout(wait_seconds):
                return await future
        except TimeoutError:
            return None
    finally:
        if future is not None:
            pending.pop(prefix, None)


async def _sync_repeater_skip_if_healthy(
    self: MeshCoreNocClockManager,
    repeater_id: str,
    *,
    fleet_sync_run_id: str | None = None,
) -> ClockSyncResult:
    """Do not reboot or write a repeater already inside the sync tolerance."""
    assert _PREVIOUS_SYNC is not None
    started_at = self._utc_now()
    try:
        target = self.resolve_target(repeater_id)
    except Exception:
        return await _PREVIOUS_SYNC(
            self, repeater_id, fleet_sync_run_id=fleet_sync_run_id
        )

    try:
        pre_check = await self.async_check_clock(
            target.stable_id,
            sync_operation=True,
            bypass_cooldown=True,
        )
    except Exception:  # noqa: BLE001 - existing recovery path may still succeed
        return await _PREVIOUS_SYNC(
            self, repeater_id, fleet_sync_run_id=fleet_sync_run_id
        )

    if (
        pre_check.state is ClockCheckState.COMPLETED
        and pre_check.clock_offset_seconds is not None
        and abs(pre_check.clock_offset_seconds) <= _SYNC_TOLERANCE_SECONDS
    ):
        beta8._clear_sync_log(self, target.stable_id)
        beta8._append_sync_line(
            self,
            target.stable_id,
            (
                f"Authenticated pre-check: offset {pre_check.clock_offset_seconds:+d} s "
                f"(RTT {float(pre_check.clock_rtt_ms or 0) / 1000.0:.1f} s)."
            ),
        )
        beta8._append_sync_line(
            self,
            target.stable_id,
            "Already within ±30 s; no reboot or clock write was required.",
        )
        response = ClockSyncResult(
            stable_id=target.stable_id,
            pubkey_prefix=target.pubkey_prefix,
            result=ClockSyncState.SUCCESS,
            started_at=started_at,
            pre_sync_offset_seconds=pre_check.clock_offset_seconds,
            post_sync_offset_seconds=pre_check.clock_offset_seconds,
        )
        return beta8._finish_with_transcript(self, response, ClockSyncState.SUCCESS)

    return await _PREVIOUS_SYNC(
        self, repeater_id, fleet_sync_run_id=fleet_sync_run_id
    )


def _start_automatic_sync_password_safe(
    self: FleetClockSyncOrchestrator,
    trigger: FleetClockSyncTrigger,
) -> None:
    """Refuse unattended sync when one or more managed repeaters lack a password."""
    assert _PREVIOUS_AUTO_SYNC_START is not None
    if trigger is not FleetClockSyncTrigger.AUTOMATIC:
        return _PREVIOUS_AUTO_SYNC_START(self, trigger)

    missing = [
        target.label
        for target in self.clock_manager.targets.values()
        if beta8._password_for(self.clock_manager, target.stable_id) is None
    ]
    if not missing:
        return _PREVIOUS_AUTO_SYNC_START(self, trigger)

    now = self._utc_now()
    self._last_summary = {
        "run_id": None,
        "trigger": FleetClockSyncTrigger.AUTOMATIC,
        "state": FleetClockSyncState.FAILED,
        "started_at": now,
        "completed_at": now,
        "duration_seconds": 0.0,
        "total_repeaters": len(self.clock_manager.targets),
        "current_repeater": None,
        "completed_count": 0,
        "successful": 0,
        "already_ahead": 0,
        "failed": len(missing),
        "skipped": len(self.clock_manager.targets),
        "per_repeater": [],
        "error": (
            "Automatic clock sync not started: saved administrator password missing for "
            + ", ".join(missing)
        ),
    }
    self._notify()
    self._save_later()


def install_epoch_sync() -> None:
    """Install beta14, then add latency correction and production automation guards."""
    global _PREVIOUS_RAW_HANDLER
    global _PREVIOUS_EXECUTE_COMMAND
    global _PREVIOUS_SYNC
    global _PREVIOUS_REMOTE_COMMAND
    global _PREVIOUS_AUTO_SYNC_START

    beta14.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    _PREVIOUS_RAW_HANDLER = MeshCoreNocClockManager._async_handle_raw_event
    _PREVIOUS_EXECUTE_COMMAND = beta8._execute_meshcore_command
    _PREVIOUS_SYNC = MeshCoreNocClockManager.async_sync_repeater_clock
    _PREVIOUS_REMOTE_COMMAND = beta8._send_remote_command
    _PREVIOUS_AUTO_SYNC_START = FleetClockSyncOrchestrator._start_background

    beta8._execute_meshcore_command = _execute_meshcore_command_with_probe
    beta8._send_remote_command = _send_remote_command_latency_aware
    MeshCoreNocClockManager._async_handle_raw_event = _async_handle_raw_event_latency_aware
    MeshCoreNocClockManager.async_sync_repeater_clock = _sync_repeater_skip_if_healthy
    FleetClockSyncOrchestrator._start_background = _start_automatic_sync_password_safe
    config_flow_module._selection_schema = _clean_selection_schema

    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


__all__ = ("install_epoch_sync",)
