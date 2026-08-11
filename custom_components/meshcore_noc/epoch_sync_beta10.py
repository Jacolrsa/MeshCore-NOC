"""MeshCore NOC beta10 anti-replay-safe clock operations.

Clock checks use MeshCore's anonymous BASIC request so they do not depend on a
repeater administrator session or CLI replay timestamps.

Clock synchronisation resets the repeater *before* correcting an ahead-running
companion. This prevents the repeater from remembering a future companion
timestamp and rejecting later commands after the companion has been repaired.
A bounded recovery path handles repeaters already stranded by beta9: if normal
password login cannot confirm but a blank ACL login proves the companion is an
existing administrator, NOC sends ``clkreboot`` as a plain admin message with a
one-shot future timestamp. The timestamp is transient because clkreboot
immediately reboots the repeater and its replay timestamp is not persisted.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from homeassistant.core import callback

from . import epoch_sync_beta8 as beta8
from . import epoch_sync_beta9 as beta9
from .clock import (
    ClockAttemptOutcome,
    ClockCheckFleetCollisionError,
    ClockCheckInProgressError,
    ClockCheckState,
    ClockManagerError,
    ClockSyncResult,
    ClockSyncState,
    MeshCoreNocClockManager,
    UnknownManagedRepeaterError,
    calculate_clock_offset,
    classify_clock_status,
)
from .const import MESHCORE_DOMAIN

_LOGGER = logging.getLogger(__name__)

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta10_installed"
_SUCCESSFUL_SYNC_OFFSET_SECONDS = 30
_CLOCK_SYNC_REPLY_GRACE_SECONDS = 4
_RECOVERY_MIN_FUTURE_SECONDS = 86_400
_RECOVERY_CONTACT_MARGIN_SECONDS = 3_600
_MAX_UINT32_SAFE = 0xFFFFFF00

_PREVIOUS_RAW_HANDLER: Any = None


def install_epoch_sync() -> None:
    """Install beta9 foundations, then beta10 clock-check and replay fixes."""
    global _PREVIOUS_RAW_HANDLER

    beta9.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    _PREVIOUS_RAW_HANDLER = MeshCoreNocClockManager._async_handle_raw_event
    MeshCoreNocClockManager._async_handle_raw_event = _async_handle_raw_event
    MeshCoreNocClockManager.async_check_clock = _async_check_clock_anon
    MeshCoreNocClockManager.async_sync_repeater_clock = _async_sync_repeater_clock
    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


def _login_payloads(manager: MeshCoreNocClockManager) -> dict[str, dict[str, Any]]:
    return manager.__dict__.setdefault("_beta10_login_payloads", {})


@callback
def _async_handle_raw_event(self: MeshCoreNocClockManager, event: Any) -> None:
    """Capture LOGIN_SUCCESS detail, then preserve beta8/beta9 event handling."""
    data = getattr(event, "data", {})
    event_type = data.get("event_type")
    payload = data.get("payload")
    if event_type == "EventType.LOGIN_SUCCESS" and isinstance(payload, dict):
        prefix = str(payload.get("pubkey_prefix") or "").lower()
        if not prefix:
            pending = beta8._pending_logins(self)
            if len(pending) == 1:
                prefix = next(iter(pending))
        if prefix:
            _login_payloads(self)[prefix] = dict(payload)

    if _PREVIOUS_RAW_HANDLER is not None:
        _PREVIOUS_RAW_HANDLER(self, event)


def _service_data(target: Any, command: str) -> dict[str, Any]:
    data: dict[str, Any] = {"command": command}
    if target.meshcore_config_entry_id:
        data["entry_id"] = target.meshcore_config_entry_id
    return data


async def _execute_service(
    manager: MeshCoreNocClockManager,
    target: Any,
    command: str,
) -> dict[str, Any]:
    response = await manager.hass.services.async_call(
        MESHCORE_DOMAIN,
        "execute_command",
        _service_data(target, command),
        blocking=True,
        return_response=True,
    )
    if not isinstance(response, dict):
        return {"error": "unstructured_response", "command": command}
    return response


def _format_remote_epoch(epoch: int) -> str:
    remote = datetime.fromtimestamp(epoch, tz=UTC)
    return (
        f"{remote.hour:02d}:{remote.minute:02d}:{remote.second:02d} - "
        f"{remote.day}/{remote.month}/{remote.year} UTC"
    )


async def _async_check_clock_anon(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
):
    """Read a repeater clock with the anonymous BASIC request.

    This avoids CLI/login replay state completely and returns as soon as the
    repeater's binary response arrives.
    """
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

    future = asyncio.get_running_loop().create_future()
    self._pending[prefix] = SimpleNamespace(
        target=target,
        requested_at=requested_at,
        started_monotonic=started_monotonic,
        future=future,
    )
    self.last_request = {
        "stable_id": stable_id,
        "pubkey_prefix": target.pubkey_prefix,
        "requested_at": requested_at,
        "command": "anonymous BASIC clock request",
    }
    self._notify(stable_id)

    try:
        result.state = ClockCheckState.SENT
        self._notify(stable_id)
        command = f"req_basic_sync({json.dumps(target.pubkey_prefix)})"

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await _execute_service(self, target, command)
        except TimeoutError:
            response = {"error": "no_response", "command": "req_basic_sync"}
        except Exception as err:  # noqa: BLE001 - HA/MeshCore service boundary
            return self._finish_failure(
                self._pending[prefix], f"anonymous clock request failed: {err}"
            )

        result.service_response = response
        if response.get("error"):
            completed_at = self._utc_now()
            error_code = str(response.get("error"))
            if error_code == "no_response":
                result.state = ClockCheckState.TIMED_OUT
                result.error = "anonymous clock response timed out"
                result.last_clock_attempt_outcome = ClockAttemptOutcome.TIMEOUT
            else:
                result.state = ClockCheckState.FAILED
                result.error = f"anonymous clock request failed: {error_code}"
                result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
            result.last_clock_attempt_error = result.error
            if result.state is ClockCheckState.TIMED_OUT:
                self.last_timeout = {
                    "stable_id": stable_id,
                    "pubkey_prefix": target.pubkey_prefix,
                    "requested_at": requested_at,
                    "timed_out_at": completed_at,
                }
            self._append_history(result, requested_at, completed_at)
            self._notify(stable_id)
            return result

        data_hex = response.get("data")
        if not isinstance(data_hex, str):
            return self._finish_failure(
                self._pending[prefix],
                "anonymous clock response did not contain binary data",
            )
        try:
            raw = bytes.fromhex(data_hex)
        except ValueError:
            return self._finish_failure(
                self._pending[prefix],
                "anonymous clock response was not valid hexadecimal",
            )
        if len(raw) < 4:
            return self._finish_failure(
                self._pending[prefix],
                "anonymous clock response was too short",
            )

        repeater_epoch = int.from_bytes(raw[:4], "little", signed=False)
        received_at = self._utc_now()
        result.state = ClockCheckState.COMPLETED
        result.last_clock_reply = received_at
        result.response_text = _format_remote_epoch(repeater_epoch)
        result.sender_timestamp = repeater_epoch
        result.clock_rtt_ms = max(
            0, round((self._monotonic() - started_monotonic) * 1000)
        )
        result.clock_offset_seconds = calculate_clock_offset(
            repeater_epoch, received_at
        )
        warning, critical = (
            self._clock_thresholds(result.stable_id)
            if self._clock_thresholds is not None
            else (120, 300)
        )
        result.clock_status = classify_clock_status(
            result.clock_offset_seconds, warning, critical
        )
        result.error = None
        result.last_successful_clock_check = received_at
        result.last_clock_attempt_outcome = ClockAttemptOutcome.SUCCESS
        result.last_clock_attempt_error = None
        self.last_response = {
            "stable_id": stable_id,
            "pubkey_prefix": target.pubkey_prefix,
            "received_at": received_at,
            "sender_timestamp": repeater_epoch,
            "response_mode": "anonymous_basic",
            "features": raw[4] if len(raw) > 4 else None,
        }
        self.last_parse_result = {
            "stable_id": stable_id,
            "success": True,
            "parsed_epoch": repeater_epoch,
            "clock_offset_seconds": result.clock_offset_seconds,
        }
        self._append_history(result, requested_at, received_at, include_reply=True)
        self._notify(stable_id)
        if not future.done():
            future.set_result(result)
        return result
    finally:
        self._pending.pop(prefix, None)


async def _send_login_with_detail(
    manager: MeshCoreNocClockManager,
    target: Any,
    password: str,
    *,
    timeout_seconds: float | None = None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    prefix = target.pubkey_prefix.lower()
    _login_payloads(manager).pop(prefix, None)
    accepted, error = await beta8._send_login(
        manager,
        target,
        password,
        timeout_seconds=timeout_seconds,
    )
    payload = _login_payloads(manager).pop(prefix, None)
    return accepted, error, payload


def _login_is_admin(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("is_admin") is True:
        return True
    permissions = payload.get("acl_permissions")
    return isinstance(permissions, int) and (permissions & 0x03) == 0x03


async def _recovery_timestamp(
    manager: MeshCoreNocClockManager,
    target: Any,
    companion_epoch: int,
) -> tuple[int, str]:
    """Choose a one-shot timestamp safely above known stale replay state."""
    now_epoch = int(manager._utc_now().timestamp())
    candidate = max(
        now_epoch + _RECOVERY_MIN_FUTURE_SECONDS,
        int(companion_epoch) + _RECOVERY_MIN_FUTURE_SECONDS,
    )
    source = "HA/companion + 24h"

    try:
        contacts = await beta9._fresh_contacts(manager, target)
        matching = [
            contact
            for contact in contacts
            if str(contact.get("public_key") or "").lower().startswith(
                target.pubkey_prefix.lower()
            )
        ]
        if matching:
            contact = matching[0]
            contact_candidates: list[int] = []
            for key in ("last_advert", "lastmod"):
                value = contact.get(key)
                if isinstance(value, (int, float)):
                    contact_candidates.append(
                        int(value) + _RECOVERY_CONTACT_MARGIN_SECONDS
                    )
            if contact_candidates and max(contact_candidates) > candidate:
                candidate = max(contact_candidates)
                source = "target contact timestamp + 1h"
    except Exception as err:  # noqa: BLE001 - recovery remains bounded
        _LOGGER.debug("Unable to inspect target contact for replay recovery: %s", err)

    candidate = min(candidate, _MAX_UINT32_SAFE)
    return candidate, source


async def _send_recovery_clkreboot(
    manager: MeshCoreNocClockManager,
    target: Any,
    companion_epoch: int,
) -> int:
    """Send clkreboot as a plain admin message with an explicit future stamp."""
    recovery_epoch, source = await _recovery_timestamp(
        manager, target, companion_epoch
    )
    beta8._append_sync_line(
        manager,
        target.stable_id,
        (
            "Anti-replay recovery: sending clkreboot as an authenticated plain "
            f"admin message with transient timestamp {recovery_epoch} ({source})."
        ),
    )
    command = (
        f"send_msg({json.dumps(target.pubkey_prefix)}, "
        f"{json.dumps('clkreboot')}, {recovery_epoch})"
    )
    await beta9._execute_response(manager, target, command)
    beta8._append_sync_line(
        manager,
        target.stable_id,
        "Recovery clkreboot was accepted for radio transmission.",
    )
    return recovery_epoch


async def _async_sync_repeater_clock(
    self: MeshCoreNocClockManager,
    repeater_id: str,
    *,
    fleet_sync_run_id: str | None = None,
) -> ClockSyncResult:
    """Reset replay state, repair companion UTC, clock-sync repeater, verify."""
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
    beta8._clear_sync_log(self, target.stable_id)

    if (
        self._fleet_sync_run_id is not None
        and fleet_sync_run_id != self._fleet_sync_run_id
    ):
        beta8._append_sync_line(
            self, target.stable_id, "Sync blocked: fleet synchronisation is active."
        )
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock synchronization is already active",
        )
    if self._fleet_run_id is not None:
        beta8._append_sync_line(
            self, target.stable_id, "Sync blocked: fleet clock check is active."
        )
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock check is already active",
        )
    if prefix in self._pending_sync or prefix in self._pending:
        beta8._append_sync_line(
            self, target.stable_id, "Sync blocked: another clock operation is active."
        )
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "another clock operation is already running for this repeater",
        )

    password = beta8._password_for(self, target.stable_id)
    if password is None:
        message = (
            "Repeater password not configured. Save the administrator password "
            "in Repeater access before synchronising the clock."
        )
        beta8._append_sync_line(
            self, target.stable_id, "Password required before clock synchronisation."
        )
        return beta8._finish_with_transcript(
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
    gate_future.set_result("beta10-sync-gate")
    self._pending_sync[prefix] = SimpleNamespace(
        target=target,
        started_at=started_at,
        future=gate_future,
    )
    beta8._capture_targets(self)[prefix] = target.stable_id
    beta8._remote_errors(self).pop(prefix, None)

    try:
        beta8._append_sync_line(
            self,
            target.stable_id,
            "Starting anti-replay-safe clock synchronisation from Home Assistant UTC.",
        )

        try:
            pre_check = await self.async_check_clock(
                target.stable_id,
                sync_operation=True,
                bypass_cooldown=True,
            )
            if (
                pre_check.state is ClockCheckState.COMPLETED
                and pre_check.clock_offset_seconds is not None
            ):
                response.pre_sync_offset_seconds = pre_check.clock_offset_seconds
                result_state.offset_before_sync_seconds = pre_check.clock_offset_seconds
                beta8._append_sync_line(
                    self,
                    target.stable_id,
                    f"Repeater pre-check offset: {pre_check.clock_offset_seconds:+d} s.",
                )
            else:
                beta8._append_sync_line(
                    self,
                    target.stable_id,
                    f"Repeater pre-check unavailable: {pre_check.error or pre_check.state}.",
                )
        except Exception as err:  # noqa: BLE001 - informational pre-check
            beta8._append_sync_line(
                self, target.stable_id, f"Repeater pre-check unavailable: {err}."
            )

        companion_epoch, companion_offset = await beta9._verify_companion(self, target)
        beta8._append_sync_line(
            self,
            target.stable_id,
            (
                f"Companion before repeater reset: epoch {companion_epoch}; "
                f"offset {companion_offset:+d} s."
            ),
        )

        beta8._append_sync_line(
            self,
            target.stable_id,
            "Authenticating to repeater before changing companion time…",
        )
        accepted, login_error, login_payload = await _send_login_with_detail(
            self, target, password
        )
        recovery_mode = False

        if accepted and not _login_is_admin(login_payload):
            error = "Saved password logged in but did not grant administrator permission."
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.UNAUTHORIZED, error
            )

        if not accepted:
            beta8._append_sync_line(
                self,
                target.stable_id,
                (
                    "Password login did not confirm. Checking whether this companion "
                    "is already a saved administrator so stale replay state can be recovered…"
                ),
            )
            acl_ok, _, acl_payload = await _send_login_with_detail(
                self, target, "", timeout_seconds=min(8, self.timeout_seconds)
            )
            if acl_ok and _login_is_admin(acl_payload):
                recovery_mode = True
                beta8._append_sync_line(
                    self,
                    target.stable_id,
                    "Existing administrator ACL confirmed; anti-replay recovery is available.",
                )
            else:
                error = (
                    login_error
                    or "Repeater login failed and no existing administrator ACL recovery was available."
                )
                beta8._append_sync_line(self, target.stable_id, error)
                return beta8._finish_with_transcript(
                    self, response, ClockSyncState.UNAUTHORIZED, error
                )
        else:
            beta8._append_sync_line(
                self, target.stable_id, "Administrator password login accepted."
            )

        if recovery_mode:
            await _send_recovery_clkreboot(self, target, companion_epoch)
        else:
            beta8._append_sync_line(
                self,
                target.stable_id,
                "Sending clkreboot before changing companion time…",
            )
            await beta8._send_remote_command(self, target, "clkreboot")
            beta8._append_sync_line(
                self,
                target.stable_id,
                "clkreboot accepted for transmission; repeater replay state will reset on reboot.",
            )

        companion_result = await beta9._ensure_companion_clock(
            self,
            target,
            allow_contact_repair=True,
            transcript_stable_id=target.stable_id,
        )
        if not companion_result.get("success"):
            reason = str(
                companion_result.get("reason") or "companion clock repair failed"
            )
            beta8._append_sync_line(
                self,
                target.stable_id,
                f"Repeater sync cancelled: companion clock is not safe ({reason}).",
            )
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, reason
            )

        beta8._append_sync_line(
            self,
            target.stable_id,
            "Companion time is verified; waiting only until repeater password login succeeds…",
        )
        accepted, login_error = await beta8._login_after_reboot(
            self, target, password
        )
        if not accepted:
            error = login_error or "post-reboot repeater login failed"
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.UNAUTHORIZED, error
            )
        beta8._append_sync_line(
            self,
            target.stable_id,
            "Post-reboot administrator login accepted.",
        )

        beta8._remote_errors(self).pop(prefix, None)
        reply = await beta8._send_remote_command(
            self,
            target,
            "clock sync",
            reply_timeout=_CLOCK_SYNC_REPLY_GRACE_SECONDS,
        )
        if reply:
            beta8._append_sync_line(
                self, target.stable_id, f"clock sync response: {reply}"
            )
        else:
            beta8._append_sync_line(
                self,
                target.stable_id,
                "clock sync sent; verifying immediately with anonymous clock read.",
            )

        remote_error = beta8._remote_errors(self).pop(prefix, None)
        if remote_error is not None:
            error_kind, text = remote_error
            state = (
                ClockSyncState.UNAUTHORIZED
                if error_kind == "unauthorized"
                else ClockSyncState.COMMAND_FAILED
            )
            beta8._append_sync_line(
                self, target.stable_id, f"Repeater reported an error: {text}"
            )
            return beta8._finish_with_transcript(self, response, state, text)

        post_check = await self.async_check_clock(
            target.stable_id,
            sync_operation=True,
            bypass_cooldown=True,
        )
        if post_check.state is not ClockCheckState.COMPLETED:
            error = post_check.error or "post-sync clock verification did not complete"
            beta8._append_sync_line(
                self, target.stable_id, f"Post-sync clock check failed: {error}"
            )
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, error
            )

        response.post_sync_offset_seconds = post_check.clock_offset_seconds
        result_state.offset_after_sync_seconds = post_check.clock_offset_seconds
        offset = post_check.clock_offset_seconds
        if offset is None:
            error = "post-sync clock offset is unknown"
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, error
            )

        beta8._append_sync_line(
            self, target.stable_id, f"Clock verified. Offset is {offset:+d} s."
        )
        if abs(offset) > _SUCCESSFUL_SYNC_OFFSET_SECONDS:
            error = (
                f"verification failed: repeater remains {offset:+d} s from Home Assistant UTC"
            )
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self, response, ClockSyncState.VERIFICATION_FAILED, error
            )

        beta8._append_sync_line(
            self, target.stable_id, "Clock synchronisation completed successfully."
        )
        return beta8._finish_with_transcript(
            self, response, ClockSyncState.SUCCESS
        )

    except asyncio.CancelledError:
        beta8._append_sync_line(
            self, target.stable_id, "Clock synchronisation cancelled."
        )
        return beta8._finish_with_transcript(
            self, response, ClockSyncState.CANCELLED, "clock sync cancelled"
        )
    except ClockManagerError as err:
        beta8._append_sync_line(
            self, target.stable_id, f"Clock operation failed: {err}"
        )
        return beta8._finish_with_transcript(
            self, response, ClockSyncState.FAILED, str(err)
        )
    except Exception as err:  # noqa: BLE001 - public service/radio boundary
        _LOGGER.exception(
            "Unexpected beta10 clock sync failure for stable_id=%s",
            target.stable_id,
        )
        beta8._append_sync_line(
            self, target.stable_id, f"Unexpected sync failure: {err}"
        )
        return beta8._finish_with_transcript(
            self, response, ClockSyncState.FAILED, str(err)
        )
    finally:
        beta8._pending_logins(self).pop(prefix, None)
        beta8._pending_remote_replies(self).pop(prefix, None)
        beta8._capture_targets(self).pop(prefix, None)
        beta8._remote_errors(self).pop(prefix, None)
        _login_payloads(self).pop(prefix, None)
        self._pending_sync.pop(prefix, None)
        result_state.sync_running = False
        self._notify(target.stable_id)
        if task is not None:
            self._sync_tasks.discard(task)
