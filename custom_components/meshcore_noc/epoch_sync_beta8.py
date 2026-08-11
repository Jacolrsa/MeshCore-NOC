"""Home Assistant UTC based repeater clock synchronisation.

This module installs the authenticated UTC synchronisation workflow on the
existing clock manager without exposing repeater passwords. It deliberately
uses only the public ``meshcore.execute_command`` Home Assistant service and
the public ``meshcore_raw_event`` event stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

from .clock import (
    ClockCheckState,
    ClockSyncResult,
    ClockSyncState,
    MeshCoreNocClockManager,
    UnknownManagedRepeaterError,
)
from .const import DOMAIN, MESHCORE_DOMAIN
from .fleet_clock import FleetClockOrchestrator

_LOGGER = logging.getLogger(__name__)

# clkreboot intentionally sends no reply. Start probing again after a short
# boot window, then let LOGIN_SUCCESS itself tell us when the repeater is ready.
_POST_REBOOT_INITIAL_SECONDS = 2
_POST_REBOOT_LOGIN_TIMEOUT_SECONDS = 6
_POST_REBOOT_LOGIN_ATTEMPTS = 3
_POST_REBOOT_RETRY_SECONDS = 1

# The MeshCore documentation does not promise a reply for ``time <epoch>``.
# If firmware does reply, continue immediately; otherwise verify after this
# short grace period instead of sleeping a fixed 10 seconds.
_TIME_REPLY_GRACE_SECONDS = 4

_LOGIN_SUCCESS_EVENT = "EventType.LOGIN_SUCCESS"
_LOGIN_FAILED_EVENT = "EventType.LOGIN_FAILED"
_CONTACT_MESSAGE_EVENT = "EventType.CONTACT_MSG_RECV"
_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta8_installed"
_FLEET_PATCH_MARKER = "_meshcore_noc_response_driven_delays_installed"

_ORIGINAL_RAW_HANDLER = MeshCoreNocClockManager._async_handle_raw_event
_ORIGINAL_FLEET_INIT = FleetClockOrchestrator.__init__


def install_epoch_sync() -> None:
    """Install the UTC and response-driven workflow exactly once."""
    if not getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        MeshCoreNocClockManager.async_sync_repeater_clock = _async_sync_repeater_clock
        MeshCoreNocClockManager._async_handle_raw_event = _async_handle_raw_event
        setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)

    # Older beta configuration stored 15/30 second fleet pauses. A completed
    # radio transaction is already our serialization boundary, so production
    # runs dispatch the next repeater immediately once the prior result is
    # terminal. Persisted options are left untouched for rollback compatibility.
    if not getattr(FleetClockOrchestrator, _FLEET_PATCH_MARKER, False):
        FleetClockOrchestrator.__init__ = _response_driven_fleet_init
        setattr(FleetClockOrchestrator, _FLEET_PATCH_MARKER, True)


def _response_driven_fleet_init(
    self: FleetClockOrchestrator,
    hass: Any,
    clock_manager: MeshCoreNocClockManager,
    config: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Construct fleet checks without artificial inter-repeater sleeps."""
    config = replace(config, success_delay_seconds=0, failure_delay_seconds=0)
    _ORIGINAL_FLEET_INIT(self, hass, clock_manager, config, *args, **kwargs)


def _management_store(manager: MeshCoreNocClockManager) -> Any | None:
    """Resolve this manager's private management store at call time."""
    config_entries = getattr(manager.hass, "config_entries", None)
    if config_entries is None or not hasattr(config_entries, "async_entries"):
        return None
    for entry in config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None and getattr(runtime, "clock_manager", None) is manager:
            return getattr(runtime, "management_store", None)
    return None


def _password_for(manager: MeshCoreNocClockManager, stable_id: str) -> str | None:
    """Read a password only inside the backend private boundary."""
    store = _management_store(manager)
    if store is None or not hasattr(store, "password_for"):
        return None
    return store.password_for(stable_id)


def _sync_logs(manager: MeshCoreNocClockManager) -> dict[str, list[str]]:
    return manager.__dict__.setdefault("_epoch_sync_logs", {})


def _pending_logins(manager: MeshCoreNocClockManager) -> dict[str, asyncio.Future[bool]]:
    return manager.__dict__.setdefault("_epoch_pending_logins", {})


def _pending_remote_replies(
    manager: MeshCoreNocClockManager,
) -> dict[str, asyncio.Future[str]]:
    return manager.__dict__.setdefault("_epoch_pending_remote_replies", {})


def _capture_targets(manager: MeshCoreNocClockManager) -> dict[str, str]:
    return manager.__dict__.setdefault("_epoch_sync_capture_targets", {})


def _remote_errors(manager: MeshCoreNocClockManager) -> dict[str, tuple[str, str]]:
    return manager.__dict__.setdefault("_epoch_sync_remote_errors", {})


def _sync_transcript(manager: MeshCoreNocClockManager, stable_id: str) -> str:
    return "\n".join(_sync_logs(manager).get(stable_id, ()))


def _clear_sync_log(manager: MeshCoreNocClockManager, stable_id: str) -> None:
    _sync_logs(manager)[stable_id] = []
    state = manager.result_for(stable_id)
    if state is not None:
        state.last_sync_response = None
        manager._notify(stable_id)


def _append_sync_line(
    manager: MeshCoreNocClockManager, stable_id: str, message: str
) -> None:
    """Publish a small, password-safe operator transcript."""
    timestamp = manager._utc_now().strftime("%H:%M:%S")
    lines = _sync_logs(manager).setdefault(stable_id, [])
    lines.append(f"{timestamp} · {message}")
    del lines[:-20]
    state = manager.result_for(stable_id)
    if state is not None:
        state.last_sync_response = "\n".join(lines)
        manager._notify(stable_id)


def _service_data(target: Any, command: str) -> dict[str, Any]:
    data: dict[str, Any] = {"command": command}
    if target.meshcore_config_entry_id:
        data["entry_id"] = target.meshcore_config_entry_id
    return data


async def _execute_meshcore_command(
    manager: MeshCoreNocClockManager,
    target: Any,
    command: str,
) -> dict[str, Any]:
    if not manager.hass.services.has_service(MESHCORE_DOMAIN, "execute_command"):
        raise HomeAssistantError("meshcore.execute_command unavailable")
    try:
        response = await manager.hass.services.async_call(
            MESHCORE_DOMAIN,
            "execute_command",
            _service_data(target, command),
            blocking=True,
            return_response=True,
        )
    except (HomeAssistantError, ServiceNotFound):
        raise
    except Exception as err:  # noqa: BLE001 - public service boundary
        raise HomeAssistantError(f"MeshCore service call failed: {err}") from err
    if not isinstance(response, dict):
        raise HomeAssistantError("MeshCore send confirmation unavailable")
    if response.get("error"):
        raise HomeAssistantError(f"MeshCore send failed: {response['error']}")
    return response


async def _send_login(
    manager: MeshCoreNocClockManager,
    target: Any,
    password: str,
    *,
    timeout_seconds: float | None = None,
) -> tuple[bool, str | None]:
    """Authenticate and await LOGIN_SUCCESS/LOGIN_FAILED."""
    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    pending = _pending_logins(manager)
    pending[prefix] = future
    command = (
        f"send_login({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(password)})"
    )
    try:
        await _execute_meshcore_command(manager, target, command)
        try:
            async with asyncio.timeout(timeout_seconds or manager.timeout_seconds):
                accepted = await future
        except TimeoutError:
            return (
                False,
                "No repeater login confirmation was received. Check the saved "
                "password and radio path.",
            )
        if not accepted:
            return False, "The repeater rejected the saved administrator password."
        return True, None
    finally:
        pending.pop(prefix, None)


async def _login_after_reboot(
    manager: MeshCoreNocClockManager,
    target: Any,
    password: str,
) -> tuple[bool, str | None]:
    """Probe for the repeater and continue as soon as login succeeds."""
    await asyncio.sleep(_POST_REBOOT_INITIAL_SECONDS)
    last_error: str | None = None
    for attempt in range(1, _POST_REBOOT_LOGIN_ATTEMPTS + 1):
        _append_sync_line(
            manager,
            target.stable_id,
            f"Re-authenticating after reboot (attempt {attempt})…",
        )
        accepted, error = await _send_login(
            manager,
            target,
            password,
            timeout_seconds=_POST_REBOOT_LOGIN_TIMEOUT_SECONDS,
        )
        if accepted:
            return True, None
        last_error = error
        if error and "rejected" in error.casefold():
            return False, error
        if attempt < _POST_REBOOT_LOGIN_ATTEMPTS:
            _append_sync_line(
                manager,
                target.stable_id,
                "Repeater not ready yet; retrying shortly…",
            )
            await asyncio.sleep(_POST_REBOOT_RETRY_SECONDS)
    return False, last_error or "post-reboot repeater login failed"


async def _send_remote_command(
    manager: MeshCoreNocClockManager,
    target: Any,
    remote_command: str,
    *,
    reply_timeout: float | None = None,
) -> str | None:
    """Send one remote command and optionally await its contact-message reply."""
    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[str] | None = None
    pending = _pending_remote_replies(manager)
    if reply_timeout is not None:
        future = asyncio.get_running_loop().create_future()
        pending[prefix] = future
    command = (
        f"send_cmd({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(remote_command)})"
    )
    try:
        await _execute_meshcore_command(manager, target, command)
        if future is None:
            return None
        try:
            async with asyncio.timeout(reply_timeout):
                return await future
        except TimeoutError:
            return None
    finally:
        if future is not None:
            pending.pop(prefix, None)


def _finish_with_transcript(
    manager: MeshCoreNocClockManager,
    response: ClockSyncResult,
    result: ClockSyncState,
    error: str | None = None,
) -> ClockSyncResult:
    response.remote_response_text = _sync_transcript(manager, response.stable_id)
    return manager._finish_sync(response, result, error)


async def _async_sync_repeater_clock(
    self: MeshCoreNocClockManager,
    repeater_id: str,
    *,
    fleet_sync_run_id: str | None = None,
) -> ClockSyncResult:
    """Reset, authenticate, push HA UTC epoch, then verify immediately."""
    started_at = self._utc_now()
    try:
        target = self.resolve_target(repeater_id)
    except UnknownManagedRepeaterError as err:
        return ClockSyncResult(
            stable_id=repeater_id,
            pubkey_prefix=None,
            result=ClockSyncState.UNRESOLVED,
            started_at=started_at,
            completed_at=self._utc_now(),
            duration_seconds=0.0,
            error=str(err),
        )

    prefix = target.pubkey_prefix.lower()
    response = ClockSyncResult(
        stable_id=target.stable_id,
        pubkey_prefix=target.pubkey_prefix,
        result=ClockSyncState.FAILED,
        started_at=started_at,
    )
    _clear_sync_log(self, target.stable_id)

    if self._fleet_sync_run_id is not None and fleet_sync_run_id != self._fleet_sync_run_id:
        _append_sync_line(self, target.stable_id, "Sync blocked: fleet synchronisation is active.")
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock synchronization is already active",
        )
    if self._fleet_run_id is not None:
        _append_sync_line(self, target.stable_id, "Sync blocked: fleet clock check is active.")
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock check is already active",
        )
    if prefix in self._pending_sync or prefix in self._pending:
        _append_sync_line(self, target.stable_id, "Sync blocked: another clock operation is active.")
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "another clock operation is already running for this repeater",
        )

    password = _password_for(self, target.stable_id)
    if password is None:
        message = (
            "Repeater password not configured. Save the administrator password "
            "in Repeater access before synchronising the clock."
        )
        _append_sync_line(self, target.stable_id, "Password required before clock synchronisation.")
        return _finish_with_transcript(
            self, response, ClockSyncState.UNAUTHORIZED, message
        )

    task = asyncio.current_task()
    if task is not None:
        self._sync_tasks.add(task)
    result_state = self._results[target.stable_id]
    result_state.sync_running = True
    result_state.last_sync_error = None
    result_state.offset_before_sync_seconds = result_state.clock_offset_seconds
    response.pre_sync_offset_seconds = result_state.clock_offset_seconds
    self._notify(target.stable_id)

    gate_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    gate_future.set_result("epoch-sync-gate")
    self._pending_sync[prefix] = SimpleNamespace(
        target=target,
        started_at=started_at,
        future=gate_future,
    )
    _capture_targets(self)[prefix] = target.stable_id
    _remote_errors(self).pop(prefix, None)

    try:
        _append_sync_line(
            self,
            target.stable_id,
            "Starting clock sync from Home Assistant UTC time.",
        )
        _append_sync_line(self, target.stable_id, "Authenticating to repeater…")
        accepted, login_error = await _send_login(self, target, password)
        if not accepted:
            _append_sync_line(self, target.stable_id, login_error or "Repeater login failed.")
            return _finish_with_transcript(
                self,
                response,
                ClockSyncState.UNAUTHORIZED,
                login_error or "repeater login failed",
            )
        _append_sync_line(self, target.stable_id, "Administrator login accepted.")

        _append_sync_line(
            self,
            target.stable_id,
            "Sending clkreboot to reset the clock and reboot the repeater…",
        )
        await _send_remote_command(self, target, "clkreboot")
        _append_sync_line(
            self,
            target.stable_id,
            "clkreboot sent. Waiting only for the repeater to become reachable again…",
        )

        accepted, login_error = await _login_after_reboot(self, target, password)
        if not accepted:
            _append_sync_line(
                self,
                target.stable_id,
                login_error or "Post-reboot login failed.",
            )
            return _finish_with_transcript(
                self,
                response,
                ClockSyncState.UNAUTHORIZED,
                login_error or "post-reboot repeater login failed",
            )
        _append_sync_line(self, target.stable_id, "Post-reboot login accepted; continuing immediately.")

        _remote_errors(self).pop(prefix, None)
        now = self._utc_now()
        epoch_seconds = int(now.timestamp())
        readable_utc = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        _append_sync_line(
            self,
            target.stable_id,
            f"Sending Home Assistant time {readable_utc} (epoch {epoch_seconds})…",
        )
        time_reply = await _send_remote_command(
            self,
            target,
            f"time {epoch_seconds}",
            reply_timeout=_TIME_REPLY_GRACE_SECONDS,
        )
        if time_reply is not None:
            _append_sync_line(
                self,
                target.stable_id,
                "Time command reply received; continuing immediately.",
            )
        else:
            _append_sync_line(
                self,
                target.stable_id,
                "No time-command reply received; verifying the clock now.",
            )

        remote_error = _remote_errors(self).pop(prefix, None)
        if remote_error is not None:
            error_kind, text = remote_error
            state = (
                ClockSyncState.UNAUTHORIZED
                if error_kind == "unauthorized"
                else ClockSyncState.COMMAND_FAILED
            )
            _append_sync_line(self, target.stable_id, f"Repeater reported an error: {text}")
            return _finish_with_transcript(self, response, state, text)

        _append_sync_line(self, target.stable_id, "Checking repeater clock to verify new time…")
        try:
            post_check = await self.async_check_clock(
                target.stable_id,
                sync_operation=True,
                bypass_cooldown=True,
            )
        except Exception as err:  # noqa: BLE001 - verification boundary
            _append_sync_line(self, target.stable_id, f"Verification failed: {err}")
            return _finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, str(err)
            )
        if post_check.state is not ClockCheckState.COMPLETED:
            error = f"post-sync clock check failed: {post_check.error or post_check.state}"
            _append_sync_line(self, target.stable_id, error)
            return _finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, error
            )

        response.post_sync_offset_seconds = post_check.clock_offset_seconds
        result_state.offset_after_sync_seconds = post_check.clock_offset_seconds
        offset = post_check.clock_offset_seconds
        offset_text = "unknown" if offset is None else f"{offset:+d} s"
        _append_sync_line(self, target.stable_id, f"Clock verified. Offset is {offset_text}.")
        _append_sync_line(self, target.stable_id, "Clock synchronisation completed successfully.")
        return _finish_with_transcript(self, response, ClockSyncState.SUCCESS)
    except asyncio.CancelledError:
        _append_sync_line(self, target.stable_id, "Clock synchronisation cancelled.")
        return _finish_with_transcript(
            self, response, ClockSyncState.CANCELLED, "clock sync cancelled"
        )
    except (HomeAssistantError, ServiceNotFound) as err:
        _append_sync_line(self, target.stable_id, f"Command failed: {err}")
        return _finish_with_transcript(
            self, response, ClockSyncState.COMMAND_FAILED, str(err)
        )
    except Exception as err:  # noqa: BLE001 - bounded sync boundary
        _LOGGER.exception(
            "Unexpected repeater clock sync failure for stable_id=%s",
            target.stable_id,
        )
        _append_sync_line(self, target.stable_id, f"Unexpected sync failure: {err}")
        return _finish_with_transcript(self, response, ClockSyncState.FAILED, str(err))
    finally:
        _pending_logins(self).pop(prefix, None)
        _pending_remote_replies(self).pop(prefix, None)
        _capture_targets(self).pop(prefix, None)
        _remote_errors(self).pop(prefix, None)
        self._pending_sync.pop(prefix, None)
        result_state.sync_running = False
        self._notify(target.stable_id)
        if task is not None:
            self._sync_tasks.discard(task)


@callback
def _async_handle_raw_event(
    self: MeshCoreNocClockManager, event: Any
) -> None:
    """Correlate login/sync replies on the Home Assistant event-loop thread."""
    data = getattr(event, "data", {})
    event_type = data.get("event_type")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        _ORIGINAL_RAW_HANDLER(self, event)
        return

    prefix = str(payload.get("pubkey_prefix", "")).lower()
    pending_logins = _pending_logins(self)
    if event_type in {_LOGIN_SUCCESS_EVENT, _LOGIN_FAILED_EVENT}:
        future = pending_logins.get(prefix)
        if future is None and len(pending_logins) == 1:
            future = next(iter(pending_logins.values()))
        if future is not None and not future.done():
            future.set_result(event_type == _LOGIN_SUCCESS_EVENT)
        return

    if event_type == _CONTACT_MESSAGE_EVENT:
        stable_id = _capture_targets(self).get(prefix)
        text = payload.get("text")
        if (
            stable_id is not None
            and prefix not in self._pending
            and isinstance(text, str)
            and text.strip()
        ):
            bounded = text.strip()[:180]
            _append_sync_line(self, stable_id, f"Repeater replied: {bounded}")
            remote_future = _pending_remote_replies(self).get(prefix)
            if remote_future is not None and not remote_future.done():
                remote_future.set_result(bounded)
            lowered = bounded.casefold()
            if (
                "unauthorized" in lowered
                or "permission" in lowered
                or "auth" in lowered
            ):
                _remote_errors(self)[prefix] = ("unauthorized", bounded)
            elif lowered.startswith("err") or "error" in lowered:
                _remote_errors(self)[prefix] = ("command", bounded)

    # The original handler correlates normal ``clock`` replies. Because this
    # wrapper is explicitly @callback, its listener runs on HA's event loop;
    # the result future completes immediately instead of later timing out.
    _ORIGINAL_RAW_HANDLER(self, event)
