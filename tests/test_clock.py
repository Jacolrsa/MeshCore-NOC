"""Tests for manual event-driven Clock Intelligence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.meshcore_noc.clock import (
    ClockAttemptOutcome,
    ClockCheckCooldownError,
    ClockCheckFleetCollisionError,
    ClockCheckInProgressError,
    ClockCheckState,
    ClockStatus,
    ClockTarget,
    MeshCoreNocClockManager,
    UnknownManagedRepeaterError,
    calculate_clock_offset,
    classify_clock_status,
    parse_clock_text,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """Keep pure manager tests independent of the incompatible HA fixture."""
    yield


class _FakeBus:
    def __init__(self) -> None:
        self.listeners = {}

    def async_listen(self, event_type, listener):
        self.listeners[event_type] = listener
        return lambda: self.listeners.pop(event_type, None)

    def fire_raw(self, payload, event_type="EventType.CONTACT_MSG_RECV"):
        self.listeners["meshcore_raw_event"](
            SimpleNamespace(data={"event_type": event_type, "payload": payload})
        )


class _FakeServices:
    def __init__(self) -> None:
        self.available = True
        self.response = {"expected_ack": "1234"}
        self.async_call = AsyncMock(side_effect=self._call)

    def has_service(self, domain, service):
        return self.available and (domain, service) == ("meshcore", "execute_command")

    async def _call(self, *args, **kwargs):
        return self.response


class _FakeHass:
    def __init__(self) -> None:
        self.bus = _FakeBus()
        self.services = _FakeServices()


def _target(prefix="a1b2c3d4e5f6", stable_id="entry_repeater_a1b2c3d4e5f6"):
    return ClockTarget(stable_id, prefix, "entry")


def _manager(
    *targets,
    cooldown=0,
    timeout=0.1,
    now=None,
    monotonic_time=None,
    managed_repeaters=None,
):
    hass = _FakeHass()
    mapped = {target.stable_id: target for target in targets or (_target(),)}
    kwargs = {}
    if now is not None:
        kwargs["now"] = now
    if monotonic_time is not None:
        kwargs["monotonic_time"] = monotonic_time
    manager = MeshCoreNocClockManager(
        hass,
        mapped,
        managed_repeaters=managed_repeaters,
        cooldown_seconds=cooldown,
        timeout_seconds=timeout,
        **kwargs,
    )
    manager.async_start()
    return hass, manager


def _reply(prefix, sender_timestamp):
    clock = datetime.fromtimestamp(sender_timestamp, UTC)
    return {
        "pubkey_prefix": prefix,
        "text": (
            f"{clock.hour:02d}:{clock.minute:02d} - "
            f"{clock.day}/{clock.month}/{clock.year} UTC"
        ),
        "sender_timestamp": sender_timestamp,
        "SNR": 7.5,
    }


def test_clock_parser_and_offset_calculation() -> None:
    """The public clock text and signed offset semantics are deterministic."""
    parsed = parse_clock_text("07:13 - 28/7/2026 UTC")
    assert parsed == datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    with pytest.raises(ValueError):
        parse_clock_text("28 July 2026 07:13")
    received = datetime(2026, 7, 28, 7, 13, 10, tzinfo=UTC)
    assert calculate_clock_offset(int(received.timestamp()) + 45, received) == 45
    assert calculate_clock_offset(int(received.timestamp()) - 45, received) == -45
    assert classify_clock_status(30) is ClockStatus.GREEN
    assert classify_clock_status(-31) is ClockStatus.YELLOW
    assert classify_clock_status(121) is ClockStatus.ORANGE
    assert classify_clock_status(-301) is ClockStatus.RED
    assert classify_clock_status(91, 90, 180) is ClockStatus.ORANGE
    assert classify_clock_status(-181, 90, 180) is ClockStatus.RED


@pytest.mark.asyncio
async def test_successful_reply_and_duplicate_ignored() -> None:
    """One correlated raw reply completes once and records signed clock data."""
    received = datetime(2026, 7, 28, 7, 13, 10, tzinfo=UTC)
    ticks = iter((10.0, 10.25))
    hass, manager = _manager(
        now=lambda: received,
        monotonic_time=lambda: next(ticks),
    )
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    sender_timestamp = int(received.timestamp()) + 45
    payload = _reply("a1b2c3d4e5f6", sender_timestamp)
    hass.bus.fire_raw(payload)
    result = await task

    assert result.state is ClockCheckState.COMPLETED
    assert result.clock_offset_seconds == 45
    assert result.clock_status is ClockStatus.YELLOW
    assert result.clock_rtt_ms == 250
    call = hass.services.async_call.await_args
    assert call.args[:2] == ("meshcore", "execute_command")
    assert call.args[2] == {
        "command": 'send_cmd a1b2c3d4e5f6 "clock"',
    }
    assert set(call.args[2]) == {"command"}
    assert call.kwargs == {"blocking": True, "return_response": True}
    assert len(manager.history) == 1
    hass.bus.fire_raw(payload)
    assert len(manager.history) == 1


@pytest.mark.asyncio
async def test_reply_during_service_call_remains_completed() -> None:
    """A fast public reply cannot be overwritten by the later send result."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    hass, manager = _manager(now=lambda: now)

    async def reply_before_return(*args, **kwargs):
        hass.bus.fire_raw(_reply("a1b2c3d4e5f6", int(now.timestamp()) + 5))
        return {"expected_ack": "1234"}

    hass.services.async_call.side_effect = reply_before_return
    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    assert result.state is ClockCheckState.COMPLETED
    assert result.clock_offset_seconds == 5


@pytest.mark.asyncio
async def test_malformed_reply_fails_without_clock_value() -> None:
    """Malformed public text is recorded but never becomes a clock result."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    hass, manager = _manager(now=lambda: now)
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    hass.bus.fire_raw(
        {
            "pubkey_prefix": "a1b2c3d4e5f6",
            "text": "not a clock",
            "sender_timestamp": int(now.timestamp()),
        }
    )
    result = await task
    assert result.state is ClockCheckState.FAILED
    assert result.clock_status is ClockStatus.UNKNOWN
    assert result.clock_offset_seconds is None
    assert manager.last_parse_result["success"] is False


@pytest.mark.asyncio
async def test_timeout_cleans_outstanding_request() -> None:
    """A missing reply times out and removes the per-target pending entry."""
    _, manager = _manager(timeout=0.001)
    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    assert result.state is ClockCheckState.TIMED_OUT
    assert manager.outstanding_requests == []
    assert manager.last_timeout["stable_id"] == result.stable_id


@pytest.mark.asyncio
async def test_successful_clock_value_is_retained_after_timeout() -> None:
    """A later timeout updates attempt metadata without erasing good data."""
    now = datetime(2026, 7, 28, 7, 13, 10, tzinfo=UTC)
    hass, manager = _manager(now=lambda: now, timeout=0.001)
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    hass.bus.fire_raw(_reply("a1b2c3d4e5f6", int(now.timestamp()) + 45))
    result = await task
    successful_at = result.last_successful_clock_check

    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")

    assert result.state is ClockCheckState.TIMED_OUT
    assert result.clock_offset_seconds == 45
    assert result.clock_status is ClockStatus.YELLOW
    assert result.last_successful_clock_check == successful_at
    assert result.last_clock_attempt_outcome is ClockAttemptOutcome.TIMEOUT
    assert result.last_clock_attempt_error == "clock response timed out"


@pytest.mark.asyncio
async def test_successful_clock_value_is_retained_after_service_failure() -> None:
    """A service failure cannot replace the latest successful reading."""
    now = datetime(2026, 7, 28, 7, 13, 10, tzinfo=UTC)
    hass, manager = _manager(now=lambda: now)
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    hass.bus.fire_raw(_reply("a1b2c3d4e5f6", int(now.timestamp()) - 301))
    result = await task
    hass.services.available = False

    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")

    assert result.clock_offset_seconds == -301
    assert result.clock_status is ClockStatus.RED
    assert result.last_clock_attempt_outcome is ClockAttemptOutcome.FAILED
    assert "unavailable" in result.last_clock_attempt_error


@pytest.mark.asyncio
async def test_unknown_only_before_first_success_and_malformed_is_separate() -> None:
    """Malformed attempts remain distinct and never manufacture clock data."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    hass, manager = _manager(now=lambda: now)
    result = manager.result_for("entry_repeater_a1b2c3d4e5f6")
    assert result.clock_status is ClockStatus.UNKNOWN
    assert result.last_successful_clock_check is None

    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    hass.bus.fire_raw(
        {
            "pubkey_prefix": "a1b2c3d4e5f6",
            "text": "invalid",
            "sender_timestamp": int(now.timestamp()),
        }
    )
    result = await task

    assert result.clock_status is ClockStatus.UNKNOWN
    assert result.last_clock_attempt_outcome is ClockAttemptOutcome.MALFORMED
    assert result.last_successful_clock_check is None


def test_fleet_clock_health_counts_and_critical_names() -> None:
    """Fleet health uses retained readings and identifies actionable names."""
    targets = (
        ClockTarget("green", "111111111111", "entry", "Aurora"),
        ClockTarget("orange", "222222222222", "entry", "Laguna2"),
        ClockTarget("red", "333333333333", "entry", "Vredenburg"),
        ClockTarget("unknown", "444444444444", "entry", "Saldanha"),
    )
    _, manager = _manager(*targets)
    manager.result_for("green").clock_status = ClockStatus.GREEN
    manager.result_for("orange").clock_status = ClockStatus.ORANGE
    manager.result_for("red").clock_status = ClockStatus.RED

    assert manager.fleet_health == {
        "in_sync": 1,
        "minor_drift": 0,
        "drift": 1,
        "critical": 1,
        "unknown": 1,
        "drift_repeaters": ["Laguna2"],
        "critical_repeaters": ["Vredenburg"],
    }


@pytest.mark.asyncio
async def test_unknown_repeater_and_unavailable_service() -> None:
    """Only addressable managed repeaters can use the public MeshCore service."""
    hass, manager = _manager()
    with pytest.raises(
        UnknownManagedRepeaterError,
        match=r"'unknown': managed=False, addressable=False",
    ):
        await manager.async_check_clock("unknown")
    hass.services.available = False
    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    assert result.state is ClockCheckState.FAILED
    assert "unavailable" in result.error


@pytest.mark.asyncio
async def test_exact_pubkey_prefix_fallback_resolves_unique_managed_target() -> None:
    """An exact unique prefix remains a compatibility input."""
    target = _target("01c1a4fa32c6", "noc-stable-laguna")
    hass, manager = _manager(target, timeout=0.001)

    result = await manager.async_check_clock("01c1a4fa32c6")

    assert result.stable_id == "noc-stable-laguna"
    assert hass.services.async_call.await_args.args[2]["command"] == (
        'send_cmd 01c1a4fa32c6 "clock"'
    )


@pytest.mark.asyncio
async def test_friendly_name_is_rejected_with_clear_valid_targets() -> None:
    """A mutable display name is never accepted as command identity."""
    target = ClockTarget("noc-stable-laguna", "01c1a4fa32c6", "entry", "Laguna2")
    _, manager = _manager(target, managed_repeaters={"noc-stable-laguna": "Laguna2"})

    with pytest.raises(UnknownManagedRepeaterError) as error:
        await manager.async_check_clock("Laguna2")

    message = str(error.value)
    assert "'Laguna2'" in message
    assert "managed=False" in message
    assert "addressable=False" in message
    assert "noc-stable-laguna (Laguna2)" in message


@pytest.mark.asyncio
async def test_managed_non_addressable_repeater_has_explicit_error() -> None:
    """A selected device without command identity is reported as managed."""
    _, manager = _manager(managed_repeaters={"managed-client": "Handset"})

    with pytest.raises(
        UnknownManagedRepeaterError,
        match=r"'managed-client': managed=True, addressable=False",
    ):
        await manager.async_check_clock("managed-client")


def test_ambiguous_pubkey_prefix_fallback_is_rejected() -> None:
    """Compatibility input cannot choose between duplicate exact prefixes."""
    first = _target("01c1a4fa32c6", "stable-a")
    second = _target("01c1a4fa32c6", "stable-b")
    _, manager = _manager(first, second)

    with pytest.raises(UnknownManagedRepeaterError):
        manager.resolve_target("01c1a4fa32c6")


def test_unmanaged_repeater_stable_id_is_rejected() -> None:
    """A real-looking but unselected stable ID is not addressable."""
    _, manager = _manager()

    with pytest.raises(
        UnknownManagedRepeaterError,
        match=r"'112233445566': managed=False, addressable=False",
    ):
        manager.resolve_target("112233445566")


@pytest.mark.asyncio
async def test_service_call_failure() -> None:
    """A Home Assistant service exception becomes a bounded failed result."""
    hass, manager = _manager()
    hass.services.async_call.side_effect = RuntimeError("transport boundary failed")
    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    assert result.state is ClockCheckState.FAILED
    assert "transport boundary failed" in result.error


@pytest.mark.asyncio
async def test_missing_send_confirmation_does_not_claim_sent() -> None:
    """A response-less service call is not promoted to MSG_SENT."""
    hass, manager = _manager()
    hass.services.response = None
    result = await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    assert result.state is ClockCheckState.FAILED
    assert result.error == "MeshCore send confirmation unavailable"


@pytest.mark.asyncio
async def test_same_target_concurrency_lock_and_cooldown() -> None:
    """One target is single-flight and retains a conservative cooldown."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    current_tick = 100.0
    hass, manager = _manager(
        cooldown=300,
        now=lambda: now,
        monotonic_time=lambda: current_tick,
    )
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    with pytest.raises(ClockCheckInProgressError):
        await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
    hass.bus.fire_raw(_reply("a1b2c3d4e5f6", int(now.timestamp())))
    await task
    with pytest.raises(ClockCheckCooldownError):
        await manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")


@pytest.mark.asyncio
async def test_manual_check_is_rejected_when_target_is_in_fleet_queue() -> None:
    """Fleet reservations prevent manual reordering or overlap."""
    _, manager = _manager()
    stable_id = "entry_repeater_a1b2c3d4e5f6"
    manager.reserve_fleet_targets("fleet-run", (stable_id,))

    with pytest.raises(ClockCheckFleetCollisionError, match="queued or running"):
        await manager.async_check_clock(stable_id)

    manager.release_fleet_targets("fleet-run")


@pytest.mark.asyncio
async def test_two_repeaters_complete_independently() -> None:
    """Different managed repeaters can have simultaneous pending reads."""
    first = _target("a1b2c3d4e5f6", "entry_repeater_a1b2c3d4e5f6")
    second = _target("112233445566", "entry_repeater_112233445566")
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    hass, manager = _manager(first, second, now=lambda: now)
    first_task = asyncio.create_task(manager.async_check_clock(first.stable_id))
    second_task = asyncio.create_task(manager.async_check_clock(second.stable_id))
    await asyncio.sleep(0)
    assert len(manager.outstanding_requests) == 2
    hass.bus.fire_raw(_reply(second.pubkey_prefix, int(now.timestamp()) + 121))
    hass.bus.fire_raw(_reply(first.pubkey_prefix, int(now.timestamp()) - 31))
    first_result, second_result = await asyncio.gather(first_task, second_task)
    assert first_result.clock_offset_seconds == -31
    assert second_result.clock_offset_seconds == 121
    assert manager.outstanding_requests == []


@pytest.mark.asyncio
async def test_irrelevant_raw_event_is_ignored() -> None:
    """Only EventType.CONTACT_MSG_RECV can satisfy a pending request."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    hass, manager = _manager(timeout=0.001, now=lambda: now)
    task = asyncio.create_task(manager.async_check_clock("entry_repeater_a1b2c3d4e5f6"))
    await asyncio.sleep(0)
    hass.bus.fire_raw(
        _reply("a1b2c3d4e5f6", int(now.timestamp())),
        event_type="EventType.MSG_SENT",
    )
    result = await task
    assert result.state is ClockCheckState.TIMED_OUT


@pytest.mark.asyncio
async def test_history_is_bounded_to_twenty_checks() -> None:
    """The in-memory operational history cannot grow without bound."""
    now = datetime(2026, 7, 28, 7, 13, tzinfo=UTC)
    tick = 0.0

    def monotonic_time():
        return tick

    hass, manager = _manager(now=lambda: now, monotonic_time=monotonic_time)
    for _ in range(21):
        task = asyncio.create_task(
            manager.async_check_clock("entry_repeater_a1b2c3d4e5f6")
        )
        await asyncio.sleep(0)
        hass.bus.fire_raw(_reply("a1b2c3d4e5f6", int(now.timestamp())))
        await task
        tick += 1
    assert len(manager.history) == 20
