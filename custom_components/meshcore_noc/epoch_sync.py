"""Home Assistant UTC based repeater clock synchronisation.

This module installs a bounded synchronisation workflow on the existing clock
manager without exposing repeater passwords. The workflow deliberately uses
only the public ``meshcore.execute_command`` Home Assistant service and the
public ``meshcore_raw_event`` event stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

from .clock import (
    ClockCheckState,
    ClockSyncResult,
    ClockSyncState,
    MeshCoreNocClockManager,
    UnknownManagedRepeaterError,
)
from .const import DOMAIN, MESHCORE_DOMAIN

_LOGGER = logging.getLogger(__name__)

_REBOOT_SETTLE_SECONDS = 10
_SET_TIME_SETTLE_SECONDS = 10
_LOGIN_SUCCESS_EVENT = "EventType.LOGIN_SUCCESS"
_LOGIN_FAILED_EVENT = "EventType.LOGIN_FAILED"
_CONTACT_MESSAGE_EVENT = "EventType.CONTACT_MSG_RECV"
_PATCH_MARKER = "_meshcore_noc_epoch_sync_installed"

_ORIGINAL_RAW_HANDLER = MeshCoreNocClockManager._async_handle_raw_event


def install_epoch_sync() -> None:
    """Install the UTC synchronisation workflow exactly once."""
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return
    MeshCoreNocClockManager.async_sync_repeater_clock = _async_sync_repeater_clock
    MeshCoreNocClockManager._async_handle_raw_event = _async_handle_raw_event
    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


def _management_store(manager: MeshCoreNocClockManager) -> Any | None:
    """Resolve this manager's private management store at call time."""
    config_entries = getattr(manager.hass, "config_entries", None)
    if config_entries is None or not hasattr(config_entries, "async_entries"):
        return None
    for entry in config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if (
            runtime is not None
            and getattr(runtime, "clock_manager", None) is manager
        ):
            return getattr(runtime, "management_store", None)
    return None


def _password_for(
    manager: MeshCoreNocClockManager, stable_id: str
) -> str | None:
    """Read a password only inside the backend private boundary."""
    store = _management_store(manager)
    if store is None or not hasattr(store, "password_for"):
        return None
    return store.password_for(stable_id)


def _sync_logs(manager: MeshCoreNocClockManager) -> dict[str, list[str]]:
    return manager.__dict__.setdefault("_epoch_sync_logs", {})


def _pending_logins(
    manager: MeshCoreNocClockManager,
) -> dict[str, asyncio.Future[bool]]:
    return manager.__dict__.setdefault("_epoch_pending_logins", {})


def _capture_targets(manager: MeshCoreNocClockManager) -> dict[str, str]:
    return manager.__dict__.setdefault("_epoch_sync_capture_targets", {})


def _remote_errors(
    manager: MeshCoreNocClockManager,
) -> dict[str, tuple[str, str]]:
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
    if not manager.hass.services.has_service(
        MESHCORE_DOMAIN, "execute_command"
    ):
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
        raise HomeAssistantError(
            f"MeshCore service call failed: {err}"
        ) from err
    if not isinstance(response, dict):
        raise HomeAssistantError("MeshCore send confirmation unavailable")
    if response.get("error"):
        raise HomeAssistantError(
            f"MeshCore send failed: {response['error']}"
        )
    return response


async def _send_login(
    manager: MeshCoreNocClockManager,
    target: Any,
    password: str,
) -> tuple[bool, str | None]:
    """Authenticate and await the asynchronous login result."""
    prefix = target.pubkey_prefix.lower()
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    pending = _pending_logins(manager)
    pending[prefix] = future
    # Functional syntax keeps whitespace and quotes in passwords safely parsed.
    command = (
        f"send_login({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(password)})"
    )
    try:
        await _execute_meshcore_command(manager, target, command)
        try:
            async with asyncio.timeout(manager.timeout_seconds):
                accepted = await future
        except TimeoutError:
            return (
                False,
                "No repeater login confirmation was received. Check the saved "
                "password and radio path.",
            )
        if not accepted:
            return (
                False,
                "The repeater rejected the saved administrator password.",
            )
        return True, None
    finally:
        pending.pop(prefix, None)


async def _send_remote_command(
    manager: MeshCoreNocClockManager,
    target: Any,
    remote_command: str,
) -> None:
    command = (
        f"send_cmd({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps(remote_command)})"
    )
    await _execute_meshcore_command(manager, target, command)


def _finish_with_transcript(
    manager: MeshCoreNocClockManager,
    response: ClockSyncResult,
    result: ClockSyncState,
    error: str | None = None,
) -> ClockSyncResult:
    response.remote_response_text = _sync_transcript(
        manager, response.stable_id
    )
    return manager._finish_sync(response, result, error)


async def _async_sync_repeater_clock(
    self: MeshCoreNocClockManager,
    repeater_id: str,
    *,
    fleet_sync_run_id: str | None = None,
) -> ClockSyncResult:
    """Reset, authenticate, push HA UTC epoch, wait, then verify."""
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

    if (
        self._fleet_sync_run_id is not None
        and fleet_sync_run_id != self._fleet_sync_run_id
    ):
        _append_sync_line(
            self,
            target.stable_id,
            "Sync blocked: fleet synchronisation is active.",
        )
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock synchronization is already active",
        )
    if self._fleet_run_id is not None:
        _append_sync_line(
            self,
            target.stable_id,
            "Sync blocked: fleet clock check is active.",
        )
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock check is already active",
        )
    if prefix in self._pending_sync or prefix in self._pending:
        _append_sync_line(
            self,
            target.stable_id,
            "Sync blocked: another clock operation is active.",
        )
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
        _append_sync_line(
            self,
            target.stable_id,
            "Password required before clock synchronisation.",
        )
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.UNAUTHORIZED,
            message,
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

    # Occupy the existing clock-operation gate. Its completed future means the
    # original raw-event handler can still process the later verification reply.
    gate_future: asyncio.Future[str] = (
        asyncio.get_running_loop().create_future()
    )
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
        _append_sync_line(
            self, target.stable_id, "Authenticating to repeater…"
        )
        accepted, login_error = await _send_login(self, target, password)
        if not accepted:
            _append_sync_line(
                self,
                target.stable_id,
                login_error or "Repeater login failed.",
            )
            return _finish_with_transcript(
                self,
                response,
                ClockSyncState.UNAUTHORIZED,
                login_error or "repeater login failed",
            )
        _append_sync_line(
            self, target.stable_id, "Administrator login accepted."
        )

        _append_sync_line(
            self,
            target.stable_id,
            "Sending clkreboot to reset the clock and reboot the repeater…",
        )
        await _send_remote_command(self, target, "clkreboot")
        _append_sync_line(
            self,
            target.stable_id,
            f"clkreboot sent. Waiting {_REBOOT_SETTLE_SECONDS} s for reboot…",
        )
        await asyncio.sleep(_REBOOT_SETTLE_SECONDS)

        # Reboot clears the remote administration session, so authenticate again.
        _append_sync_line(
            self, target.stable_id, "Re-authenticating after reboot…"
        )
        accepted, login_error = await _send_login(self, target, password)
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
        _append_sync_line(
            self, target.stable_id, "Post-reboot login accepted."
        )

        _remote_errors(self).pop(prefix, None)
        epoch_seconds = int(self._utc_now().timestamp())
        readable_utc = self._utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
        _append_sync_line(
            self,
            target.stable_id,
            (
                f"Sending Home Assistant time {readable_utc} "
                f"(epoch {epoch_seconds})…"
            ),
        )
        await _send_remote_command(self, target, f"time {epoch_seconds}")
        _append_sync_line(
            self,
            target.stable_id,
            (
                f"Time command sent. Waiting {_SET_TIME_SETTLE_SECONDS} s "
                "before verification…"
            ),
        )
        await asyncio.sleep(_SET_TIME_SETTLE_SECONDS)

        remote_error = _remote_errors(self).pop(prefix, None)
        if remote_error is not None:
            error_kind, text = remote_error
            state = (
                ClockSyncState.UNAUTHORIZED
                if error_kind == "unauthorized"
                else ClockSyncState.COMMAND_FAILED
            )
            _append_sync_line(
                self,
                target.stable_id,
                f"Repeater reported an error: {text}",
            )
            return _finish_with_transcript(self, response, state, text)

        _append_sync_line(
            self,
            target.stable_id,
            "Checking repeater clock to verify new time…",
        )
        try:
            post_check = await self.async_check_clock(
                target.stable_id,
                sync_operation=True,
                bypass_cooldown=True,
            )
        except Exception as err:  # noqa: BLE001 - verification boundary
            _append_sync_line(
                self,
                target.stable_id,
                f"Verification failed: {err}",
            )
            return _finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                str(err),
            )
        if post_check.state is not ClockCheckState.COMPLETED:
            error = (
                "post-sync clock check failed: "
                f"{post_check.error or post_check.state}"
            )
            _append_sync_line(self, target.stable_id, error)
            return _finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                error,
            )

        response.post_sync_offset_seconds = post_check.clock_offset_seconds
        result_state.offset_after_sync_seconds = post_check.clock_offset_seconds
        offset = post_check.clock_offset_seconds
        offset_text = "unknown" if offset is None else f"{offset:+d} s"
        _append_sync_line(
            self,
            target.stable_id,
            f"Clock verified. Offset is {offset_text}.",
        )
        _append_sync_line(
            self,
            target.stable_id,
            "Clock synchronisation completed successfully.",
        )
        return _finish_with_transcript(
            self, response, ClockSyncState.SUCCESS
        )
    except asyncio.CancelledError:
        _append_sync_line(
            self, target.stable_id, "Clock synchronisation cancelled."
        )
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.CANCELLED,
            "clock sync cancelled",
        )
    except (HomeAssistantError, ServiceNotFound) as err:
        _append_sync_line(
            self, target.stable_id, f"Command failed: {err}"
        )
        return _finish_with_transcript(
            self,
            response,
            ClockSyncState.COMMAND_FAILED,
            str(err),
        )
    except Exception as err:  # noqa: BLE001 - bounded sync boundary
        _LOGGER.exception(
            "Unexpected repeater clock sync failure for stable_id=%s",
            target.stable_id,
        )
        _append_sync_line(
            self,
            target.stable_id,
            f"Unexpected sync failure: {err}",
        )
        return _finish_with_transcript(
            self, response, ClockSyncState.FAILED, str(err)
        )
    finally:
        _pending_logins(self).pop(prefix, None)
        _capture_targets(self).pop(prefix, None)
        _remote_errors(self).pop(prefix, None)
        self._pending_sync.pop(prefix, None)
        result_state.sync_running = False
        self._notify(target.stable_id)
        if task is not None:
            self._sync_tasks.discard(task)


def _async_handle_raw_event(
    self: MeshCoreNocClockManager, event: Any
) -> None:
    """Correlate login outcomes and safe sync replies, then keep old handling."""
    data = getattr(event, "data", {})
    event_type = data.get("event_type")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        _ORIGINAL_RAW_HANDLER(self, event)
        return

    prefix = str(payload.get("pubkey_prefix", "")).lower()
    pending = _pending_logins(self)
    if event_type in {_LOGIN_SUCCESS_EVENT, _LOGIN_FAILED_EVENT}:
        future = pending.get(prefix)
        if future is None and len(pending) == 1:
            future = next(iter(pending.values()))
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
            _append_sync_line(
                self, stable_id, f"Repeater replied: {bounded}"
            )
            lowered = bounded.casefold()
            if (
                "unauthorized" in lowered
                or "permission" in lowered
                or "auth" in lowered
            ):
                _remote_errors(self)[prefix] = ("unauthorized", bounded)
            elif lowered.startswith("err") or "error" in lowered:
                _remote_errors(self)[prefix] = ("command", bounded)

    _ORIGINAL_RAW_HANDLER(self, event)
