"""MeshCore NOC beta9 companion-first clock synchronisation.

The companion clock is authoritative for the repeater ``clock sync`` command.
Firmware v13 companion radios cannot move their clock backwards through
``set_time``.  If a companion is ahead because future contact ``lastmod``
timestamps are bootstrapping its RTC, this module repairs only those invalid
future ``lastmod`` values, lets them persist, reboots the companion, sets its
clock forward from Home Assistant UTC, verifies it, and only then synchronises
the repeater.

No contacts are deleted and saved repeater passwords never leave the backend.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

from . import epoch_sync_beta8 as beta8
from .clock import (
    ClockCheckState,
    ClockManagerError,
    ClockSyncResult,
    ClockSyncState,
    MeshCoreNocClockManager,
    UnknownManagedRepeaterError,
)
from .const import MESHCORE_DOMAIN

_LOGGER = logging.getLogger(__name__)

_PATCH_MARKER = "_meshcore_noc_epoch_sync_beta9_installed"
_SUCCESSFUL_SYNC_OFFSET_SECONDS = 30
_COMPANION_ACCEPTABLE_AHEAD_SECONDS = 5
_CONTACT_FUTURE_GRACE_SECONDS = 30
_CONTACT_REPAIR_BACKDATE_SECONDS = 120
_CONTACT_PERSIST_SECONDS = 6
_COMPANION_RECONNECT_TIMEOUT_SECONDS = 25
_COMPANION_REPAIR_ATTEMPTS = 3
_CLOCK_SYNC_REPLY_GRACE_SECONDS = 4

_ORIGINAL_CHECK_CLOCK = MeshCoreNocClockManager.async_check_clock
_ORIGINAL_FINISH_SYNC = MeshCoreNocClockManager._finish_sync


def install_epoch_sync() -> None:
    """Install beta8 safety patches, then the companion-first beta9 workflow."""
    beta8.install_epoch_sync()
    if getattr(MeshCoreNocClockManager, _PATCH_MARKER, False):
        return

    MeshCoreNocClockManager.async_check_clock = _async_check_clock_no_cooldown
    MeshCoreNocClockManager.async_sync_repeater_clock = _async_sync_repeater_clock
    MeshCoreNocClockManager._finish_sync = _finish_sync_success_only
    setattr(MeshCoreNocClockManager, _PATCH_MARKER, True)


async def _async_check_clock_no_cooldown(
    self: MeshCoreNocClockManager,
    stable_id: str,
    *,
    fleet_run_id: str | None = None,
    sync_operation: bool = False,
    bypass_cooldown: bool = False,
):
    """Allow a new check as soon as the previous operation is terminal."""
    return await _ORIGINAL_CHECK_CLOCK(
        self,
        stable_id,
        fleet_run_id=fleet_run_id,
        sync_operation=sync_operation,
        bypass_cooldown=True,
    )


def _finish_sync_success_only(
    self: MeshCoreNocClockManager,
    response: ClockSyncResult,
    result: ClockSyncState,
    error: str | None = None,
) -> ClockSyncResult:
    """Keep ``last_sync_time`` as the last verified successful sync only."""
    state = self.result_for(response.stable_id)
    previous_success = state.last_sync_time if state is not None else None
    finished = _ORIGINAL_FINISH_SYNC(self, response, result, error)
    state = self.result_for(response.stable_id)
    if state is not None and result is not ClockSyncState.SUCCESS:
        state.last_sync_time = previous_success
        self._notify(response.stable_id)
    return finished


def _service_data(target: Any, command: str) -> dict[str, Any]:
    data: dict[str, Any] = {"command": command}
    if target.meshcore_config_entry_id:
        data["entry_id"] = target.meshcore_config_entry_id
    return data


async def _execute_response(
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
        raise RuntimeError(f"{command} did not return structured data")
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    return response


async def _execute_no_response(
    manager: MeshCoreNocClockManager,
    target: Any,
    command: str,
) -> None:
    await manager.hass.services.async_call(
        MESHCORE_DOMAIN,
        "execute_command",
        _service_data(target, command),
        blocking=True,
        return_response=False,
    )


def _extract_epoch(response: dict[str, Any]) -> int:
    for key in ("time", "timestamp", "current_time", "epoch"):
        value = response.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    raise RuntimeError(f"Companion time missing from response: {response!r}")


async def _get_companion_time(
    manager: MeshCoreNocClockManager,
    target: Any,
) -> int:
    return _extract_epoch(await _execute_response(manager, target, "get_time"))


async def _set_companion_time_forward(
    manager: MeshCoreNocClockManager,
    target: Any,
    epoch: int,
) -> None:
    # set_time commonly returns EventType.OK with an empty payload. Calling
    # without a response avoids HA's historical None-vs-dict UI error; get_time
    # below is the authoritative verification.
    await _execute_no_response(manager, target, f"set_time({int(epoch)})")


async def _fresh_contacts(
    manager: MeshCoreNocClockManager,
    target: Any,
) -> list[dict[str, Any]]:
    # Force the SDK to read the device contact list, then return the
    # coordinator's structured representation.
    await _execute_response(manager, target, "get_contacts")
    data: dict[str, Any] = {}
    if target.meshcore_config_entry_id:
        data["entry_id"] = target.meshcore_config_entry_id
    response = await manager.hass.services.async_call(
        MESHCORE_DOMAIN,
        "get_contacts",
        data,
        blocking=True,
        return_response=True,
    )
    contacts = response.get("contacts") if isinstance(response, dict) else None
    if not isinstance(contacts, list):
        raise RuntimeError("MeshCore contact list unavailable")
    return [dict(item) for item in contacts if isinstance(item, dict)]


def _pack_contact_update(contact: dict[str, Any], lastmod: int) -> bytes:
    """Build CMD_ADD_UPDATE_CONTACT while preserving every public contact field."""
    public_key = str(contact.get("public_key") or "")
    key = bytes.fromhex(public_key)
    if len(key) != 32:
        raise ValueError("contact public key must be 32 bytes")

    contact_type = int(contact.get("type", 0))
    flags = int(contact.get("flags", 0))
    out_path_len = int(contact.get("out_path_len", -1))
    hash_mode = int(contact.get("out_path_hash_mode", -1))
    if out_path_len < 0:
        packed_path_len = 0xFF
    else:
        if not 0 <= out_path_len <= 63:
            raise ValueError("contact path length is outside the protocol range")
        packed_path_len = out_path_len | ((max(hash_mode, 0) & 0x03) << 6)

    out_path_hex = str(contact.get("out_path") or "")
    if len(out_path_hex) % 2:
        raise ValueError("contact path is not valid hexadecimal")
    out_path = bytes.fromhex(out_path_hex)
    if len(out_path) > 64:
        raise ValueError("contact path exceeds 64 bytes")
    out_path = out_path.ljust(64, b"\x00")

    name = str(contact.get("adv_name") or "").encode("utf-8")
    if len(name) > 32:
        raise ValueError("contact name exceeds the 32-byte wire field")
    name = name.ljust(32, b"\x00")

    last_advert = int(contact.get("last_advert", 0))
    lat = int(round(float(contact.get("adv_lat", 0.0)) * 1_000_000))
    lon = int(round(float(contact.get("adv_lon", 0.0)) * 1_000_000))

    return b"".join(
        (
            b"\x09",
            key,
            contact_type.to_bytes(1, "little"),
            flags.to_bytes(1, "little"),
            packed_path_len.to_bytes(1, "little"),
            out_path,
            name,
            last_advert.to_bytes(4, "little", signed=False),
            lat.to_bytes(4, "little", signed=True),
            lon.to_bytes(4, "little", signed=True),
            int(lastmod).to_bytes(4, "little", signed=False),
        )
    )


async def _send_contact_lastmod(
    manager: MeshCoreNocClockManager,
    target: Any,
    contact: dict[str, Any],
    lastmod: int,
) -> None:
    frame = _pack_contact_update(contact, lastmod)
    # execute_command accepts functional calls with typed Python literals.
    # The underlying send method is fire-and-forget here; persistence and
    # reboot verification are the acknowledgement.
    await _execute_no_response(manager, target, f"send({frame!r})")


async def _wait_for_companion(
    manager: MeshCoreNocClockManager,
    target: Any,
) -> int:
    deadline = asyncio.get_running_loop().time() + _COMPANION_RECONNECT_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            return await _get_companion_time(manager, target)
        except Exception as err:  # noqa: BLE001 - reconnect polling boundary
            last_error = err
            await asyncio.sleep(1)
    raise RuntimeError(
        "Companion did not reconnect after reboot"
        + (f": {last_error}" if last_error else "")
    )


async def _verify_companion(
    manager: MeshCoreNocClockManager,
    target: Any,
) -> tuple[int, int]:
    companion = await _get_companion_time(manager, target)
    ha_epoch = int(manager._utc_now().timestamp())
    return companion, companion - ha_epoch


def _companion_lock(manager: MeshCoreNocClockManager) -> asyncio.Lock:
    """Serialize companion repair/time setting across all repeater syncs."""
    lock = manager.__dict__.get("_beta9_companion_clock_lock")
    if lock is None:
        lock = asyncio.Lock()
        manager.__dict__["_beta9_companion_clock_lock"] = lock
    return lock


async def _ensure_companion_clock(
    manager: MeshCoreNocClockManager,
    target: Any,
    *,
    allow_contact_repair: bool,
    transcript_stable_id: str,
) -> dict[str, Any]:
    """Make the connected companion safe as the source for repeater clock sync."""
    async with _companion_lock(manager):
        return await _ensure_companion_clock_locked(
            manager,
            target,
            allow_contact_repair=allow_contact_repair,
            transcript_stable_id=transcript_stable_id,
        )


async def _ensure_companion_clock_locked(
    manager: MeshCoreNocClockManager,
    target: Any,
    *,
    allow_contact_repair: bool,
    transcript_stable_id: str,
) -> dict[str, Any]:
    device = await _execute_response(manager, target, "send_device_query")
    fw_ver = device.get("fw_ver", device.get("fw ver"))
    model = str(device.get("model") or "unknown")
    rebooted = False
    beta8._append_sync_line(
        manager,
        transcript_stable_id,
        f"Companion detected: {model}, protocol firmware {fw_ver}.",
    )

    companion, offset = await _verify_companion(manager, target)
    ha_epoch = int(manager._utc_now().timestamp())
    beta8._append_sync_line(
        manager,
        transcript_stable_id,
        f"HA epoch {ha_epoch}; companion epoch {companion}; offset {offset:+d} s.",
    )

    if offset > _COMPANION_ACCEPTABLE_AHEAD_SECONDS and not allow_contact_repair:
        return {
            "success": False,
            "reason": "companion_ahead",
            "companion_epoch": companion,
            "ha_epoch": ha_epoch,
            "offset_seconds": offset,
            "rebooted": rebooted,
        }

    if offset > _COMPANION_ACCEPTABLE_AHEAD_SECONDS:
        if not isinstance(fw_ver, int) or fw_ver < 13:
            return {
                "success": False,
                "reason": "unsupported_companion_firmware",
                "companion_epoch": companion,
                "ha_epoch": ha_epoch,
                "offset_seconds": offset,
                "rebooted": rebooted,
            }

        for attempt in range(1, _COMPANION_REPAIR_ATTEMPTS + 1):
            now_epoch = int(manager._utc_now().timestamp())
            contacts = await _fresh_contacts(manager, target)
            future = [
                contact
                for contact in contacts
                if contact.get("added_to_node") is True
                and isinstance(contact.get("lastmod"), (int, float))
                and int(contact["lastmod"]) > now_epoch + _CONTACT_FUTURE_GRACE_SECONDS
            ]
            if not future:
                beta8._append_sync_line(
                    manager,
                    transcript_stable_id,
                    "Companion is ahead but no saved future lastmod remains; automatic repair stopped.",
                )
                return {
                    "success": False,
                    "reason": "ahead_without_future_lastmod",
                    "companion_epoch": companion,
                    "ha_epoch": now_epoch,
                    "offset_seconds": companion - now_epoch,
                    "rebooted": rebooted,
                }

            future.sort(key=lambda item: int(item["lastmod"]), reverse=True)
            highest = future[0]
            beta8._append_sync_line(
                manager,
                transcript_stable_id,
                (
                    f"Repair attempt {attempt}: {len(future)} saved contact(s) have future "
                    f"lastmod values; highest is {highest.get('adv_name') or highest.get('pubkey_prefix')} "
                    f"at {int(highest['lastmod'])}."
                ),
            )

            repair_epoch = now_epoch - _CONTACT_REPAIR_BACKDATE_SECONDS
            repaired_names: list[str] = []
            for contact in future:
                await _send_contact_lastmod(manager, target, contact, repair_epoch)
                repaired_names.append(
                    str(contact.get("adv_name") or contact.get("pubkey_prefix") or "contact")
                )

            beta8._append_sync_line(
                manager,
                transcript_stable_id,
                (
                    f"Corrected {len(repaired_names)} invalid future lastmod value(s) "
                    f"to {repair_epoch}; waiting {_CONTACT_PERSIST_SECONDS} s for flash persistence."
                ),
            )
            await asyncio.sleep(_CONTACT_PERSIST_SECONDS)

            beta8._append_sync_line(
                manager,
                transcript_stable_id,
                "Rebooting companion so RTC bootstraps from the repaired contact table…",
            )
            await _execute_no_response(manager, target, "reboot")
            rebooted = True
            await asyncio.sleep(2)
            companion = await _wait_for_companion(manager, target)
            now_epoch = int(manager._utc_now().timestamp())
            offset = companion - now_epoch
            beta8._append_sync_line(
                manager,
                transcript_stable_id,
                f"Companion returned at epoch {companion}; offset is now {offset:+d} s.",
            )
            if offset <= _COMPANION_ACCEPTABLE_AHEAD_SECONDS:
                break
        else:
            return {
                "success": False,
                "reason": "future_lastmod_repair_exhausted",
                "companion_epoch": companion,
                "ha_epoch": int(manager._utc_now().timestamp()),
                "offset_seconds": offset,
                "rebooted": rebooted,
            }

    # If the companion is behind, use the supported forward-only set_time path.
    # Never try to move it backwards.
    companion, offset = await _verify_companion(manager, target)
    if offset < -1:
        target_epoch = int(manager._utc_now().timestamp())
        beta8._append_sync_line(
            manager,
            transcript_stable_id,
            f"Setting companion forward to Home Assistant epoch {target_epoch}…",
        )
        await _set_companion_time_forward(manager, target, target_epoch)
        await asyncio.sleep(0.5)

    companion, offset = await _verify_companion(manager, target)
    beta8._append_sync_line(
        manager,
        transcript_stable_id,
        f"Companion verification: epoch {companion}, offset {offset:+d} s.",
    )
    success = abs(offset) <= _COMPANION_ACCEPTABLE_AHEAD_SECONDS
    return {
        "success": success,
        "reason": None if success else "companion_verification_failed",
        "companion_epoch": companion,
        "ha_epoch": int(manager._utc_now().timestamp()),
        "offset_seconds": offset,
        "rebooted": rebooted,
    }


async def _async_sync_repeater_clock(
    self: MeshCoreNocClockManager,
    repeater_id: str,
    *,
    fleet_sync_run_id: str | None = None,
) -> ClockSyncResult:
    """Verify/fix companion UTC, then clkreboot + remote clock sync + verify."""
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

    if self._fleet_sync_run_id is not None and fleet_sync_run_id != self._fleet_sync_run_id:
        beta8._append_sync_line(self, target.stable_id, "Sync blocked: fleet synchronisation is active.")
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock synchronization is already active",
        )
    if self._fleet_run_id is not None:
        beta8._append_sync_line(self, target.stable_id, "Sync blocked: fleet clock check is active.")
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            "a fleet clock check is already active",
        )
    if prefix in self._pending_sync or prefix in self._pending:
        beta8._append_sync_line(self, target.stable_id, "Sync blocked: another clock operation is active.")
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
        beta8._append_sync_line(self, target.stable_id, "Password required before clock synchronisation.")
        return beta8._finish_with_transcript(
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

    gate_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    gate_future.set_result("companion-first-sync-gate")
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
            "Starting companion-first clock synchronisation from Home Assistant UTC.",
        )

        beta8._append_sync_line(self, target.stable_id, "Authenticating to repeater…")
        accepted, login_error = await beta8._send_login(self, target, password)
        if not accepted:
            beta8._append_sync_line(self, target.stable_id, login_error or "Repeater login failed.")
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.UNAUTHORIZED,
                login_error or "repeater login failed",
            )
        beta8._append_sync_line(self, target.stable_id, "Administrator login accepted.")

        companion_result = await _ensure_companion_clock(
            self,
            target,
            allow_contact_repair=True,
            transcript_stable_id=target.stable_id,
        )
        if not companion_result.get("success"):
            reason = str(companion_result.get("reason") or "companion clock repair failed")
            beta8._append_sync_line(
                self,
                target.stable_id,
                f"Repeater sync cancelled: companion clock is not safe ({reason}).",
            )
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                reason,
            )

        if companion_result.get("rebooted"):
            beta8._append_sync_line(
                self,
                target.stable_id,
                "Companion rebooted during repair; authenticating to the repeater again…",
            )
            accepted, login_error = await beta8._send_login(self, target, password)
            if not accepted:
                beta8._append_sync_line(
                    self,
                    target.stable_id,
                    login_error or "Repeater login failed after companion reboot.",
                )
                return beta8._finish_with_transcript(
                    self,
                    response,
                    ClockSyncState.UNAUTHORIZED,
                    login_error or "repeater login failed after companion reboot",
                )
            beta8._append_sync_line(self, target.stable_id, "Repeater login restored.")

        beta8._append_sync_line(
            self,
            target.stable_id,
            "Sending clkreboot to reset the repeater clock and reboot it…",
        )
        await beta8._send_remote_command(self, target, "clkreboot")
        beta8._append_sync_line(
            self,
            target.stable_id,
            "clkreboot sent; waiting only until the repeater accepts login again.",
        )

        accepted, login_error = await beta8._login_after_reboot(self, target, password)
        if not accepted:
            beta8._append_sync_line(
                self,
                target.stable_id,
                login_error or "Post-reboot login failed.",
            )
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.UNAUTHORIZED,
                login_error or "post-reboot repeater login failed",
            )
        beta8._append_sync_line(
            self,
            target.stable_id,
            "Post-reboot login accepted; synchronising from the verified companion clock.",
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
                self,
                target.stable_id,
                f"clock sync response: {reply}",
            )
        else:
            beta8._append_sync_line(
                self,
                target.stable_id,
                "clock sync sent; no text reply received, verifying with clock now.",
            )

        beta8._append_sync_line(self, target.stable_id, "Checking repeater clock for verification…")
        try:
            post_check = await self.async_check_clock(
                target.stable_id,
                sync_operation=True,
                bypass_cooldown=True,
            )
        except ClockManagerError as err:
            beta8._append_sync_line(
                self,
                target.stable_id,
                f"Post-sync clock check failed: {err}",
            )
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                str(err),
            )

        if post_check.state is not ClockCheckState.COMPLETED:
            error = post_check.error or "post-sync clock verification did not complete"
            beta8._append_sync_line(
                self,
                target.stable_id,
                f"Post-sync clock check failed: {error}",
            )
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                error,
            )

        response.post_sync_offset_seconds = post_check.clock_offset_seconds
        result_state.offset_after_sync_seconds = post_check.clock_offset_seconds
        offset = post_check.clock_offset_seconds
        if offset is None:
            error = "post-sync clock offset is unknown"
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                error,
            )

        beta8._append_sync_line(
            self,
            target.stable_id,
            f"Clock verified. Offset is {offset:+d} s.",
        )
        if abs(offset) > _SUCCESSFUL_SYNC_OFFSET_SECONDS:
            error = (
                f"verification failed: repeater remains {offset:+d} s from Home Assistant UTC"
            )
            beta8._append_sync_line(self, target.stable_id, error)
            return beta8._finish_with_transcript(
                self,
                response,
                ClockSyncState.VERIFICATION_FAILED,
                error,
            )

        beta8._append_sync_line(
            self,
            target.stable_id,
            "Clock synchronisation completed successfully.",
        )
        return beta8._finish_with_transcript(self, response, ClockSyncState.SUCCESS)

    except asyncio.CancelledError:
        beta8._append_sync_line(self, target.stable_id, "Clock synchronisation cancelled.")
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.CANCELLED,
            "clock sync cancelled",
        )
    except Exception as err:  # noqa: BLE001 - public service/radio boundary
        _LOGGER.exception(
            "Unexpected companion-first clock sync failure for stable_id=%s",
            target.stable_id,
        )
        beta8._append_sync_line(self, target.stable_id, f"Unexpected sync failure: {err}")
        return beta8._finish_with_transcript(
            self,
            response,
            ClockSyncState.FAILED,
            str(err),
        )
    finally:
        beta8._pending_logins(self).pop(prefix, None)
        beta8._pending_remote_replies(self).pop(prefix, None)
        beta8._capture_targets(self).pop(prefix, None)
        beta8._remote_errors(self).pop(prefix, None)
        self._pending_sync.pop(prefix, None)
        result_state.sync_running = False
        self._notify(target.stable_id)
        if task is not None:
            self._sync_tasks.discard(task)
