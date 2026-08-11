"""MeshCore NOC beta13 authenticated clock checks.

All operator clock checks now authenticate with the saved repeater administrator
password before issuing the remote ``clock`` CLI command.  There is deliberately
no anonymous BASIC fallback and no manual clock-check cooldown.

Radio loss is handled with bounded, response-driven retries: login may be
retried once when no confirmation is heard, and the authenticated ``clock``
command may be transmitted up to three times.  Any valid clock reply completes
the operation immediately.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from . import epoch_sync_beta8 as beta8
from . import epoch_sync_beta12 as beta12
from .clock import (
    ClockAttemptOutcome,
    ClockCheckFleetCollisionError,
    ClockCheckInProgressError,
    ClockCheckState,
    MeshCoreNocClockManager,
)

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta13_installed"
_LOGIN_ATTEMPTS = 2
_LOGIN_RESPONSE_TIMEOUT_SECONDS = 8
_CLOCK_ATTEMPTS = 3
_CLOCK_RESPONSE_TIMEOUT_SECONDS = 8
_RETRY_GAP_SECONDS = 1


async def _authenticated_login(
    manager: MeshCoreNocClockManager,
    target,
    password: str,
) -> tuple[bool, str | None, int]:
    """Authenticate with the stored administrator password using bounded retries."""
    last_error: str | None = None
    for attempt in range(1, _LOGIN_ATTEMPTS + 1):
        accepted, error = await beta8._send_login(
            manager,
            target,
            password,
            timeout_seconds=min(
                _LOGIN_RESPONSE_TIMEOUT_SECONDS, manager.timeout_seconds
            ),
        )
        if accepted:
            return True, None, attempt
        last_error = error
        if error and "rejected" in error.casefold():
            return False, error, attempt
        if attempt < _LOGIN_ATTEMPTS:
            await asyncio.sleep(_RETRY_GAP_SECONDS)
    return False, last_error or "No repeater login confirmation received", _LOGIN_ATTEMPTS


async def _async_check_clock_authenticated(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
):
    """Authenticate, issue ``clock``, and finish on the first valid reply.

    ``bypass_cooldown`` remains in the signature for service compatibility only;
    beta13 intentionally does not enforce a manual cooldown.
    """
    del bypass_cooldown

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

    accepted, login_error, login_attempts = await _authenticated_login(
        self, target, password
    )
    if not accepted:
        result.state = ClockCheckState.FAILED
        if login_error and "rejected" in login_error.casefold():
            result.error = "Repeater rejected the saved administrator password."
        else:
            result.error = (
                "Administrator login did not confirm after "
                f"{login_attempts} attempt(s). The repeater may be unreachable or "
                "may still have stale anti-replay state; run Sync this repeater to repair it."
            )
        result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
        result.last_clock_attempt_error = result.error
        self._append_history(result, requested_at, self._utc_now())
        self._notify(stable_id)
        return result

    future = asyncio.get_running_loop().create_future()
    pending = SimpleNamespace(
        target=target,
        requested_at=requested_at,
        started_monotonic=started_monotonic,
        future=future,
    )
    self._pending[prefix] = pending

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
            if future.done():
                return future.result()

            try:
                async with asyncio.timeout(
                    min(_CLOCK_RESPONSE_TIMEOUT_SECONDS, self.timeout_seconds)
                ):
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
            f"{_CLOCK_ATTEMPTS} attempts. Login succeeded, but the repeater did not "
            "return the clock reply; radio path may be unreliable or stale."
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
        }
        self._append_history(result, requested_at, completed_at)
        self._notify(stable_id)
        return result
    finally:
        self._pending.pop(prefix, None)


def install_epoch_sync() -> None:
    """Install beta12 foundations, then require authentication for all checks."""
    beta12.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    MeshCoreNocClockManager.async_check_clock = _async_check_clock_authenticated
    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


__all__ = ("install_epoch_sync",)
