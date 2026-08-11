"""MeshCore NOC beta14 route-aware authenticated clock operations.

Beta13 proved that administrator-password clock checks work reliably for direct
repeaters, but field measurements showed a large route-dependent timeout gap:
a direct route reported suggested_timeout=4782 while a routed repeater reported
18128. Fixed 8 second waits therefore expired before valid multi-hop replies
could reasonably return.

Beta14 keeps password authentication mandatory and the manual cooldown removed,
but derives reply windows from MeshCore's own per-transmission
``suggested_timeout``. The SDK itself converts this value using /800 for remote
login/request waits, which already includes useful radio margin.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from . import epoch_sync_beta8 as beta8
from . import epoch_sync_beta13 as beta13
from .clock import (
    ClockAttemptOutcome,
    ClockCheckFleetCollisionError,
    ClockCheckInProgressError,
    ClockCheckState,
    MeshCoreNocClockManager,
)

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta14_installed"
_ROUTE_TIMEOUT_DIVISOR = 800.0
_MIN_ROUTE_WAIT_SECONDS = 4.0
_MAX_ROUTE_WAIT_SECONDS = 90.0
_LOGIN_ATTEMPTS = 2
_CLOCK_ATTEMPTS = 2
_RETRY_GAP_SECONDS = 1.0
_POST_LOGIN_SETTLE_SECONDS = 0.75


def _route_wait_seconds(
    response: dict[str, Any] | None,
    *,
    fallback_seconds: float,
    minimum_seconds: float = _MIN_ROUTE_WAIT_SECONDS,
) -> float:
    """Convert MeshCore's route estimate to the SDK-style wait window."""
    suggested = response.get("suggested_timeout") if isinstance(response, dict) else None
    try:
        suggested_value = float(suggested)
    except (TypeError, ValueError):
        suggested_value = 0.0

    if suggested_value > 0:
        wait = suggested_value / _ROUTE_TIMEOUT_DIVISOR
    else:
        wait = float(fallback_seconds)

    wait = max(wait, float(minimum_seconds))
    return min(wait, _MAX_ROUTE_WAIT_SECONDS)


def _route_timing(manager: MeshCoreNocClockManager) -> dict[str, dict[str, Any]]:
    return manager.__dict__.setdefault("_epoch_route_timing", {})


async def _send_login_route_aware(
    manager: MeshCoreNocClockManager,
    target: Any,
    password: str,
    *,
    timeout_seconds: float | None = None,
) -> tuple[bool, str | None]:
    """Authenticate using the timeout returned for this actual radio route."""
    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    pending = beta8._pending_logins(manager)
    pending[prefix] = future
    command = (
        f"send_login({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(password)})"
    )
    try:
        response = await beta8._execute_meshcore_command(manager, target, command)
        minimum = max(_MIN_ROUTE_WAIT_SECONDS, float(timeout_seconds or 0.0))
        wait_seconds = _route_wait_seconds(
            response,
            fallback_seconds=float(timeout_seconds or manager.timeout_seconds),
            minimum_seconds=minimum,
        )
        _route_timing(manager)[prefix] = {
            "operation": "login",
            "suggested_timeout": response.get("suggested_timeout"),
            "wait_seconds": wait_seconds,
        }

        if future.done():
            accepted = future.result()
        else:
            try:
                async with asyncio.timeout(wait_seconds):
                    accepted = await future
            except TimeoutError:
                return (
                    False,
                    "No repeater login confirmation was received within the "
                    f"route-aware {wait_seconds:.1f} second window.",
                )

        if not accepted:
            return False, "The repeater rejected the saved administrator password."
        return True, None
    finally:
        pending.pop(prefix, None)


async def _send_remote_command_route_aware(
    manager: MeshCoreNocClockManager,
    target: Any,
    remote_command: str,
    *,
    reply_timeout: float | None = None,
) -> str | None:
    """Send a remote CLI command and use its route estimate when awaiting reply."""
    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[str] | None = None
    pending = beta8._pending_remote_replies(manager)
    if reply_timeout is not None:
        future = asyncio.get_running_loop().create_future()
        pending[prefix] = future

    command = (
        f"send_cmd({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(remote_command)})"
    )
    try:
        response = await beta8._execute_meshcore_command(manager, target, command)
        if future is None:
            return None

        wait_seconds = _route_wait_seconds(
            response,
            fallback_seconds=float(reply_timeout),
            minimum_seconds=max(_MIN_ROUTE_WAIT_SECONDS, float(reply_timeout)),
        )
        _route_timing(manager)[prefix] = {
            "operation": f"remote:{remote_command}",
            "suggested_timeout": response.get("suggested_timeout"),
            "wait_seconds": wait_seconds,
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


async def _async_check_clock_route_aware(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
):
    """Password-authenticated clock check using route-derived response windows."""
    del bypass_cooldown  # retained for service compatibility; no cooldown is enforced.

    target = self.resolve_target(stable_id)
    stable_id = target.stable_id
    prefix = target.pubkey_prefix.lower()

    if not sync_operation and self._fleet_sync_run_id is not None:
        raise ClockCheckFleetCollisionError(
            "A fleet clock synchronization is already active"
        )
    if not sync_operation and prefix in self._pending_sync:
        raise ClockCheckInProgressError(
            f"A clock synchronization is already pending for {stable_id}"
        )
    if stable_id in self._fleet_reserved_ids and fleet_run_id != self._fleet_run_id:
        raise ClockCheckFleetCollisionError(
            f"{stable_id!r} is queued or running in fleet clock run "
            f"{self._fleet_run_id}"
        )
    if prefix in self._pending:
        raise ClockCheckInProgressError(
            f"A clock check is already pending for {stable_id}"
        )

    requested_at = self._utc_now()
    started_monotonic = self._monotonic()
    result = self._results[stable_id]
    result.state = ClockCheckState.QUEUED
    result.last_clock_check = requested_at
    result.last_clock_attempt = requested_at
    result.last_clock_attempt_outcome = None
    result.last_clock_attempt_error = None
    result.error = None
    result.response_text = None
    result.sender_timestamp = None
    result.clock_rtt_ms = None
    result.service_response = None
    self.last_request = {
        "stable_id": stable_id,
        "pubkey_prefix": target.pubkey_prefix,
        "requested_at": requested_at,
        "command": "password login -> clock",
        "authentication": "saved administrator password",
        "timing": "MeshCore suggested_timeout / 800",
        "cooldown_enforced": False,
    }
    self._notify(stable_id)

    password = beta8._password_for(self, stable_id)
    if password is None:
        result.state = ClockCheckState.FAILED
        result.error = (
            "Repeater administrator password is not configured. Save the password "
            "in Repeater access before checking the clock."
        )
        result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
        result.last_clock_attempt_error = result.error
        self._append_history(result, requested_at, self._utc_now())
        self._notify(stable_id)
        return result

    result.state = ClockCheckState.CALLING_SERVICE
    self._notify(stable_id)

    login_error: str | None = None
    accepted = False
    for login_attempt in range(1, _LOGIN_ATTEMPTS + 1):
        accepted, login_error = await beta8._send_login(self, target, password)
        if accepted:
            break
        if login_error and "rejected" in login_error.casefold():
            break
        if login_attempt < _LOGIN_ATTEMPTS:
            await asyncio.sleep(_RETRY_GAP_SECONDS)

    if not accepted:
        result.state = ClockCheckState.FAILED
        if login_error and "rejected" in login_error.casefold():
            result.error = "Repeater rejected the saved administrator password."
        else:
            timing = _route_timing(self).get(prefix, {})
            wait = timing.get("wait_seconds")
            wait_text = f" ({float(wait):.1f} s route window)" if wait else ""
            result.error = (
                "Administrator login did not confirm after route-aware attempts"
                f"{wait_text}. The repeater may be unreachable or the stored path may be stale."
            )
        result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
        result.last_clock_attempt_error = result.error
        self._append_history(result, requested_at, self._utc_now())
        self._notify(stable_id)
        return result

    # Give the just-used route/radio queue a very small settling interval. This
    # is intentionally not a fixed long delay; successful replies still drive
    # progress immediately.
    await asyncio.sleep(_POST_LOGIN_SETTLE_SECONDS)

    future = asyncio.get_running_loop().create_future()
    pending = SimpleNamespace(
        target=target,
        requested_at=requested_at,
        started_monotonic=started_monotonic,
        future=future,
    )
    self._pending[prefix] = pending

    last_wait_seconds = float(self.timeout_seconds)
    try:
        result.state = ClockCheckState.SENT
        self._notify(stable_id)

        for attempt in range(1, _CLOCK_ATTEMPTS + 1):
            command = (
                f"send_cmd({json.dumps(target.pubkey_prefix)}, "
                f"{json.dumps('clock')})"
            )
            try:
                service_response = await beta8._execute_meshcore_command(
                    self, target, command
                )
            except Exception as err:  # noqa: BLE001 - HA/MeshCore service boundary
                result.state = ClockCheckState.FAILED
                result.error = f"Authenticated clock command failed: {err}"
                result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
                result.last_clock_attempt_error = result.error
                self._append_history(result, requested_at, self._utc_now())
                self._notify(stable_id)
                return result

            result.service_response = service_response
            last_wait_seconds = _route_wait_seconds(
                service_response,
                fallback_seconds=float(self.timeout_seconds),
            )
            self.last_request.update(
                {
                    "clock_attempt": attempt,
                    "suggested_timeout": service_response.get("suggested_timeout"),
                    "clock_wait_seconds": last_wait_seconds,
                }
            )
            _route_timing(self)[prefix] = {
                "operation": "clock",
                "attempt": attempt,
                "suggested_timeout": service_response.get("suggested_timeout"),
                "wait_seconds": last_wait_seconds,
            }

            if future.done():
                return future.result()

            try:
                async with asyncio.timeout(last_wait_seconds):
                    return await asyncio.shield(future)
            except TimeoutError:
                if future.done():
                    return future.result()
                if attempt < _CLOCK_ATTEMPTS:
                    await asyncio.sleep(_RETRY_GAP_SECONDS)
                    continue

        completed_at = self._utc_now()
        result.state = ClockCheckState.TIMED_OUT
        result.error = (
            "No authenticated clock response received after "
            f"{_CLOCK_ATTEMPTS} route-aware attempt(s). The last MeshCore wait "
            f"window was {last_wait_seconds:.1f} seconds; radio path may be unreachable or stale."
        )
        result.last_clock_attempt_outcome = ClockAttemptOutcome.TIMEOUT
        result.last_clock_attempt_error = result.error
        self.last_timeout = {
            "stable_id": stable_id,
            "pubkey_prefix": target.pubkey_prefix,
            "requested_at": requested_at,
            "timed_out_at": completed_at,
            "authenticated": True,
            "clock_attempts": _CLOCK_ATTEMPTS,
            "last_route_wait_seconds": last_wait_seconds,
        }
        self._append_history(result, requested_at, completed_at)
        self._notify(stable_id)
        return result
    finally:
        self._pending.pop(prefix, None)


def install_epoch_sync() -> None:
    """Install beta13, then replace fixed timing with MeshCore route timing."""
    beta13.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    # These helpers are also used by the beta10/beta12 synchronisation path, so
    # Sync benefits from route-aware login and command-reply timing as well.
    beta8._send_login = _send_login_route_aware
    beta8._send_remote_command = _send_remote_command_route_aware
    MeshCoreNocClockManager.async_check_clock = _async_check_clock_route_aware

    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


__all__ = ("install_epoch_sync",)
