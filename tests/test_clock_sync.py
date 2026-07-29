"""Focused tests for single-repeater Clock Intelligence synchronization."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.meshcore_noc.clock import (
    ClockCheckState,
    ClockSyncState,
    ClockTarget,
    MeshCoreNocClockManager,
)


class _FakeBus:
    def __init__(self) -> None:
        self.listeners = {}

    def async_listen(self, event_type, listener):
        self.listeners[event_type] = listener
        return lambda: self.listeners.pop(event_type, None)

    def fire_raw(self, payload, *, timestamp):
        self.listeners["meshcore_raw_event"](
            SimpleNamespace(
                data={
                    "event_type": "EventType.CONTACT_MSG_RECV",
                    "payload": payload,
                    "timestamp": timestamp,
                }
            )
        )


class _FakeServices:
    def __init__(self, hass, now) -> None:
        self.hass = hass
        self.now = now
        self.calls = []
        self.sync_reply: str | None = "OK - clock set: 07:13 - 28/7/2026 UTC"
        self.clock_offsets = [120, 1]
        self.fail_sync = False
        self.skip_post_reply = False
        self.on_sync_send = None

    def has_service(self, domain, service):
        return (domain, service) == ("meshcore", "execute_command")

    async def async_call(self, domain, service, data, **kwargs):
        self.calls.append((domain, service, data, kwargs))
        command = data["command"]
        if command.endswith('"clock"'):
            if (
                self.skip_post_reply
                and len(
                    [
                        call
                        for call in self.calls
                        if call[2]["command"].endswith('"clock"')
                    ]
                )
                > 1
            ):
                return {"expected_ack": "clock"}
            offset = self.clock_offsets.pop(0)
            sender_timestamp = int(self.now.timestamp()) + offset
            clock = datetime.fromtimestamp(sender_timestamp, UTC)
            self.hass.bus.fire_raw(
                {
                    "pubkey_prefix": "01c1a4fa32c6",
                    "text": (
                        f"{clock.hour:02d}:{clock.minute:02d} - "
                        f"{clock.day}/{clock.month}/{clock.year} UTC"
                    ),
                    "sender_timestamp": sender_timestamp,
                },
                timestamp=self.now.timestamp(),
            )
            return {"expected_ack": "clock"}
        if self.fail_sync:
            raise RuntimeError("local transport rejected command")
        if self.on_sync_send is not None:
            self.on_sync_send()
        if self.sync_reply is not None:
            self.hass.bus.fire_raw(
                {
                    "pubkey_prefix": "01c1a4fa32c6",
                    "text": self.sync_reply,
                    "sender_timestamp": int(self.now.timestamp()),
                },
                timestamp=self.now.timestamp(),
            )
        return {"expected_ack": "sync"}


class _FakeHass:
    def __init__(self, now) -> None:
        self.bus = _FakeBus()
        self.services = _FakeServices(self, now)


def _manager(*, timeout=0.05):
    now = datetime(2026, 7, 28, 7, 13, 10, tzinfo=UTC)
    hass = _FakeHass(now)
    manager = MeshCoreNocClockManager(
        hass,
        {
            "laguna-stable": ClockTarget(
                "laguna-stable",
                "01c1a4fa32c6",
                "meshcore-entry",
                "Laguna2",
            )
        },
        managed_repeaters={"laguna-stable": "Laguna2"},
        cooldown_seconds=300,
        timeout_seconds=timeout,
        now=lambda: now,
    )
    manager.async_start()
    return hass, manager, now


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remote_response",
    ("OK - clock set", "OK - clock set: 07:13 - 28/7/2026 UTC"),
)
async def test_sync_accepts_source_backed_success_responses(remote_response) -> None:
    """Both current and legacy success replies complete and verify."""
    hass, manager, _ = _manager()
    hass.services.sync_reply = remote_response

    result = await manager.async_sync_repeater_clock("laguna-stable")

    assert result.result is ClockSyncState.SUCCESS
    assert result.pre_sync_offset_seconds == 120
    assert result.post_sync_offset_seconds == 1
    assert result.remote_response_text == remote_response
    assert [call[2] for call in hass.services.calls] == [
        {"command": 'send_cmd 01c1a4fa32c6 "clock"'},
        {"command": 'send_cmd 01c1a4fa32c6 "clock sync"'},
        {"command": 'send_cmd 01c1a4fa32c6 "clock"'},
    ]
    assert all(set(call[2]) == {"command"} for call in hass.services.calls)
    state = manager.result_for("laguna-stable")
    assert state is not None
    assert state.last_sync_result is ClockSyncState.SUCCESS
    assert state.offset_before_sync_seconds == 120
    assert state.offset_after_sync_seconds == 1
    assert state.sync_running is False


@pytest.mark.asyncio
async def test_listener_is_ready_before_sync_command_send() -> None:
    """The exact-prefix response future exists before transmission."""
    hass, manager, _ = _manager()

    def assert_pending():
        assert "01c1a4fa32c6" in manager._pending_sync

    hass.services.on_sync_send = assert_pending
    result = await manager.async_sync_repeater_clock("laguna-stable")
    assert result.result is ClockSyncState.SUCCESS


@pytest.mark.asyncio
async def test_unresolved_and_duplicate_operation_are_rejected() -> None:
    """Only one operation may own one resolved managed repeater."""
    hass, manager, _ = _manager()
    unresolved = await manager.async_sync_repeater_clock("removed")
    assert unresolved.result is ClockSyncState.UNRESOLVED

    hass.services.sync_reply = None
    first = asyncio.create_task(manager.async_sync_repeater_clock("laguna-stable"))
    while not manager._pending_sync:
        await asyncio.sleep(0)
    duplicate = await manager.async_sync_repeater_clock("laguna-stable")
    assert duplicate.result is ClockSyncState.FAILED
    assert "already running" in duplicate.error
    first.cancel()
    cancelled = await first
    assert cancelled.result is ClockSyncState.CANCELLED


@pytest.mark.asyncio
async def test_exact_prefix_stale_and_unrelated_responses_are_ignored() -> None:
    """Only a fresh source-backed response from the exact target completes."""
    hass, manager, now = _manager()
    hass.services.sync_reply = None
    task = asyncio.create_task(manager.async_sync_repeater_clock("laguna-stable"))
    while not manager._pending_sync:
        await asyncio.sleep(0)

    hass.bus.fire_raw(
        {
            "pubkey_prefix": "01c1a4fa32c6",
            "text": "OK - clock set",
            "sender_timestamp": int(now.timestamp()),
        },
        timestamp=now.timestamp() - 1,
    )
    hass.bus.fire_raw(
        {
            "pubkey_prefix": "ffffffffffff",
            "text": "OK - clock set",
            "sender_timestamp": int(now.timestamp()),
        },
        timestamp=now.timestamp(),
    )
    hass.bus.fire_raw(
        {
            "pubkey_prefix": "01c1a4fa32c6",
            "text": "ordinary direct message",
            "sender_timestamp": int(now.timestamp()),
        },
        timestamp=now.timestamp(),
    )
    await asyncio.sleep(0)
    assert not task.done()

    hass.bus.fire_raw(
        {
            "pubkey_prefix": "01c1a4fa32c6",
            "text": "OK - clock set",
            "sender_timestamp": int(now.timestamp()),
        },
        timestamp=now.timestamp(),
    )
    result = await task
    assert result.result is ClockSyncState.SUCCESS


@pytest.mark.asyncio
async def test_forward_only_response_is_not_success() -> None:
    """Firmware refusal to move backwards maps to already_ahead."""
    hass, manager, _ = _manager()
    hass.services.sync_reply = "ERR: clock cannot go backwards"

    result = await manager.async_sync_repeater_clock("laguna-stable")

    assert result.result is ClockSyncState.ALREADY_AHEAD
    assert result.post_sync_offset_seconds is None
    assert len(hass.services.calls) == 2


@pytest.mark.asyncio
async def test_authentication_failure_is_not_retried() -> None:
    """An explicit permission response is terminal and clearly classified."""
    hass, manager, _ = _manager()
    hass.services.sync_reply = "ERR: permission denied"

    result = await manager.async_sync_repeater_clock("laguna-stable")

    assert result.result is ClockSyncState.UNAUTHORIZED
    assert result.error == "ERR: permission denied"
    assert len(hass.services.calls) == 2


@pytest.mark.asyncio
async def test_timeout_and_local_service_failure_cleanup() -> None:
    """Timeouts and local service failures leave no listener or running flag."""
    hass, manager, _ = _manager(timeout=0.001)
    hass.services.sync_reply = None
    timed_out = await manager.async_sync_repeater_clock("laguna-stable")
    assert timed_out.result is ClockSyncState.TIMEOUT
    assert manager._pending_sync == {}
    assert manager.result_for("laguna-stable").sync_running is False

    hass, manager, _ = _manager()
    hass.services.fail_sync = True
    failed = await manager.async_sync_repeater_clock("laguna-stable")
    assert failed.result is ClockSyncState.COMMAND_FAILED
    assert "local transport" in failed.error
    assert manager._pending_sync == {}


@pytest.mark.asyncio
async def test_post_sync_verification_failure() -> None:
    """A remote success without a confirming clock read is not success."""
    hass, manager, _ = _manager(timeout=0.001)
    hass.services.skip_post_reply = True

    result = await manager.async_sync_repeater_clock("laguna-stable")

    assert result.result is ClockSyncState.VERIFICATION_FAILED
    assert result.remote_response_text.startswith("OK - clock set:")
    assert result.post_sync_offset_seconds is None


@pytest.mark.asyncio
async def test_unload_cancels_operation_and_cleans_listener() -> None:
    """Integration unload cancels the operation and removes raw listeners."""
    hass, manager, _ = _manager()
    hass.services.sync_reply = None
    task = asyncio.create_task(manager.async_sync_repeater_clock("laguna-stable"))
    while not manager._pending_sync:
        await asyncio.sleep(0)

    manager.async_stop()
    result = await task

    assert result.result is ClockSyncState.CANCELLED
    assert manager._pending_sync == {}
    assert "meshcore_raw_event" not in hass.bus.listeners
    assert manager.result_for("laguna-stable").sync_running is False


@pytest.mark.asyncio
async def test_existing_read_only_clock_check_is_unchanged() -> None:
    """The established read-only service command and result remain intact."""
    hass, manager, _ = _manager()
    result = await manager.async_check_clock("laguna-stable", bypass_cooldown=True)

    assert result.state is ClockCheckState.COMPLETED
    assert hass.services.calls[0][2] == {"command": 'send_cmd 01c1a4fa32c6 "clock"'}
