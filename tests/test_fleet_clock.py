"""Tests for serialized fleet Clock Intelligence orchestration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.meshcore_noc.clock import (
    ClockCheckState,
    ClockStatus,
    ClockTarget,
)
from custom_components.meshcore_noc.fleet_clock import (
    FleetClockAlreadyRunningError,
    FleetClockConfig,
    FleetClockOrchestrator,
    FleetClockState,
    FleetClockTrigger,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """Keep pure orchestrator tests independent of Home Assistant fixtures."""
    yield


class _FakeHass:
    def async_create_task(self, coro, _name):
        return asyncio.create_task(coro)


class _FakeClockManager:
    def __init__(self, states=None, *, block=False):
        prefixes = ("111111111111", "222222222222", "333333333333")
        self.targets = {
            f"node-{index}": ClockTarget(
                f"node-{index}", prefix, "entry", f"Node {index}"
            )
            for index, prefix in enumerate(prefixes, start=1)
        }
        self.states = dict(states or {})
        self.calls = []
        self.active_calls = 0
        self.max_active_calls = 0
        self.reserved = None
        self.outstanding_requests = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not block:
            self.release.set()

    def reserve_fleet_targets(self, run_id, stable_ids):
        assert self.reserved is None
        self.reserved = (run_id, stable_ids)

    def release_fleet_targets(self, run_id):
        if self.reserved and self.reserved[0] == run_id:
            self.reserved = None

    async def async_check_clock(self, stable_id, *, fleet_run_id=None):
        assert self.reserved and fleet_run_id == self.reserved[0]
        self.calls.append(stable_id)
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        self.started.set()
        try:
            await self.release.wait()
            await asyncio.sleep(0)
            state = self.states.get(stable_id, ClockCheckState.COMPLETED)
            if isinstance(state, Exception):
                raise state
        finally:
            self.active_calls -= 1
        return SimpleNamespace(
            state=state,
            clock_offset_seconds=5 if state is ClockCheckState.COMPLETED else None,
            clock_status=(
                ClockStatus.GREEN
                if state is ClockCheckState.COMPLETED
                else ClockStatus.UNKNOWN
            ),
            error=None if state is ClockCheckState.COMPLETED else f"{state} result",
        )


def _config(
    *,
    automatic=False,
    success_delay=0,
    failure_delay=0,
    rotating=False,
):
    return FleetClockConfig(
        automatic_enabled=automatic,
        interval_hours=6,
        success_delay_seconds=success_delay,
        failure_delay_seconds=failure_delay,
        rotating_start=rotating,
    )


def _orchestrator(
    manager,
    *,
    config=None,
    delay_waiter=None,
    schedule_at=None,
):
    kwargs = {
        "now": lambda: datetime(2026, 7, 28, 9, 0, tzinfo=UTC),
        "monotonic_time": lambda: 1.0,
        "run_id_factory": lambda: "run-1",
    }
    if delay_waiter:
        kwargs["delay_waiter"] = delay_waiter
    if schedule_at:
        kwargs["schedule_at"] = schedule_at
    return FleetClockOrchestrator(
        _FakeHass(),
        manager,
        config or _config(),
        **kwargs,
    )


async def _finish(orchestrator):
    assert orchestrator._task is not None
    await orchestrator._task
    return orchestrator.current_run


@pytest.mark.asyncio
async def test_successful_three_repeater_sequence_is_exactly_one_at_a_time():
    manager = _FakeClockManager()
    orchestrator = _orchestrator(manager)

    initial = orchestrator.async_start_run()
    final = await _finish(orchestrator)

    assert initial["state"] is FleetClockState.QUEUED
    assert manager.calls == ["node-1", "node-2", "node-3"]
    assert manager.max_active_calls == 1
    assert final["state"] is FleetClockState.COMPLETED
    assert final["success_count"] == 3
    assert final["completed_count"] == 3
    assert final["remaining_count"] == 0
    assert orchestrator.progress == "3/3"
    assert orchestrator.is_active is False


@pytest.mark.asyncio
async def test_timeout_and_failure_continue_with_correct_delays():
    manager = _FakeClockManager(
        {
            "node-1": ClockCheckState.TIMED_OUT,
            "node-2": ClockCheckState.FAILED,
        }
    )
    delays = []

    async def wait_delay(seconds, _cancel_event):
        delays.append(seconds)
        return False

    orchestrator = _orchestrator(
        manager,
        config=_config(success_delay=15, failure_delay=30),
        delay_waiter=wait_delay,
    )

    final = await _finish_after_start(orchestrator)

    assert manager.calls == ["node-1", "node-2", "node-3"]
    assert delays == [30, 30]
    assert final["state"] is FleetClockState.COMPLETED_WITH_ERRORS
    assert final["timeout_count"] == 1
    assert final["failure_count"] == 1
    assert final["success_count"] == 1


@pytest.mark.asyncio
async def test_service_failure_is_recorded_and_queue_continues():
    manager = _FakeClockManager({"node-1": RuntimeError("service unavailable")})
    orchestrator = _orchestrator(manager)

    final = await _finish_after_start(orchestrator)

    assert manager.calls == ["node-1", "node-2", "node-3"]
    assert final["state"] is FleetClockState.COMPLETED_WITH_ERRORS
    assert final["failure_count"] == 1
    assert "service unavailable" in final["outcomes"][0]["error"]


async def _finish_after_start(orchestrator):
    orchestrator.async_start_run()
    return await _finish(orchestrator)


@pytest.mark.asyncio
async def test_success_delay_is_used_between_successes():
    manager = _FakeClockManager()
    delays = []

    async def wait_delay(seconds, _cancel_event):
        delays.append(seconds)
        return False

    orchestrator = _orchestrator(
        manager,
        config=_config(success_delay=15, failure_delay=30),
        delay_waiter=wait_delay,
    )
    await _finish_after_start(orchestrator)

    assert delays == [15, 15]


@pytest.mark.asyncio
async def test_second_fleet_run_is_rejected():
    manager = _FakeClockManager(block=True)
    orchestrator = _orchestrator(manager)
    orchestrator.async_start_run()
    await manager.started.wait()

    with pytest.raises(FleetClockAlreadyRunningError, match="already active"):
        orchestrator.async_start_run()

    manager.release.set()
    await _finish(orchestrator)


def test_fleet_start_is_rejected_while_single_check_is_active():
    manager = _FakeClockManager()
    manager.outstanding_requests = [{"stable_id": "node-1"}]
    orchestrator = _orchestrator(manager)

    with pytest.raises(
        FleetClockAlreadyRunningError, match="single-repeater clock check"
    ):
        orchestrator.async_start_run()


@pytest.mark.asyncio
async def test_cancel_while_current_reply_waits_does_not_interrupt_transmission():
    manager = _FakeClockManager(block=True)
    orchestrator = _orchestrator(manager)
    orchestrator.async_start_run()
    await manager.started.wait()

    cancelled = orchestrator.async_cancel_run()
    assert cancelled["state"] is FleetClockState.CANCELLING
    assert manager.active_calls == 1
    manager.release.set()
    final = await _finish(orchestrator)

    assert manager.calls == ["node-1"]
    assert final["completed_count"] == 1
    assert final["state"] is FleetClockState.CANCELLED


@pytest.mark.asyncio
async def test_cancel_during_delay_stops_before_next_dispatch():
    manager = _FakeClockManager()
    delay_started = asyncio.Event()

    async def wait_delay(_seconds, cancel_event):
        delay_started.set()
        await cancel_event.wait()
        return True

    orchestrator = _orchestrator(manager, delay_waiter=wait_delay)
    orchestrator.async_start_run()
    await delay_started.wait()
    orchestrator.async_cancel_run()
    final = await _finish(orchestrator)

    assert manager.calls == ["node-1"]
    assert final["state"] is FleetClockState.CANCELLED


@pytest.mark.asyncio
async def test_unload_cancels_task_and_releases_queue():
    manager = _FakeClockManager(block=True)
    orchestrator = _orchestrator(manager)
    orchestrator.async_start_run()
    await manager.started.wait()

    orchestrator.async_stop()
    with pytest.raises(asyncio.CancelledError):
        await orchestrator._task

    assert manager.reserved is None
    assert orchestrator.scheduler_state == "stopped"
    assert orchestrator.current_run["state"] is FleetClockState.CANCELLED


@pytest.mark.asyncio
async def test_scheduled_run_is_skipped_while_manual_run_active():
    manager = _FakeClockManager(block=True)
    scheduled = []

    def schedule_at(when, callback):
        scheduled.append((when, callback))
        return lambda: None

    orchestrator = _orchestrator(
        manager,
        config=_config(automatic=True),
        schedule_at=schedule_at,
    )
    orchestrator.async_start_scheduler()
    orchestrator.async_start_run(FleetClockTrigger.MANUAL)
    await manager.started.wait()

    orchestrator._async_scheduled_callback(datetime(2026, 7, 28, 15, 0, tzinfo=UTC))

    assert orchestrator.scheduled_runs_skipped == 1
    assert len(scheduled) == 2
    manager.release.set()
    await _finish(orchestrator)


@pytest.mark.asyncio
async def test_due_scheduler_starts_a_scheduled_run_when_idle():
    manager = _FakeClockManager()
    scheduled = []

    def schedule_at(when, callback):
        scheduled.append((when, callback))
        return lambda: None

    orchestrator = _orchestrator(
        manager,
        config=_config(automatic=True),
        schedule_at=schedule_at,
    )
    orchestrator.async_start_scheduler()

    orchestrator._async_scheduled_callback(datetime(2026, 7, 28, 15, 0, tzinfo=UTC))
    final = await _finish(orchestrator)

    assert final["trigger"] is FleetClockTrigger.SCHEDULED
    assert final["state"] is FleetClockState.COMPLETED
    assert len(scheduled) == 2


def test_automatic_mode_is_disabled_by_default():
    manager = _FakeClockManager()
    orchestrator = _orchestrator(manager)

    orchestrator.async_start_scheduler()

    assert orchestrator.scheduler_state == "disabled"
    assert orchestrator.next_scheduled_run is None


def test_scheduler_is_cancelled_for_options_reload_or_unload():
    manager = _FakeClockManager()
    unsubscribed = []

    def schedule_at(_when, _callback):
        return lambda: unsubscribed.append(True)

    orchestrator = _orchestrator(
        manager,
        config=_config(automatic=True),
        schedule_at=schedule_at,
    )
    orchestrator.async_start_scheduler()
    assert orchestrator.next_scheduled_run is not None

    orchestrator.async_stop()

    assert unsubscribed == [True]
    assert orchestrator.next_scheduled_run is None


@pytest.mark.asyncio
async def test_rotating_start_advances_after_completed_run():
    manager = _FakeClockManager()
    ids = iter(("run-1", "run-2"))
    orchestrator = FleetClockOrchestrator(
        _FakeHass(),
        manager,
        _config(rotating=True),
        run_id_factory=lambda: next(ids),
    )

    first = await _finish_after_start(orchestrator)
    second = await _finish_after_start(orchestrator)

    assert [item["stable_id"] for item in first["ordered_repeaters"]] == [
        "node-1",
        "node-2",
        "node-3",
    ]
    assert [item["stable_id"] for item in second["ordered_repeaters"]] == [
        "node-2",
        "node-3",
        "node-1",
    ]


@pytest.mark.asyncio
async def test_history_is_limited_to_twenty_runs():
    manager = _FakeClockManager()
    counter = 0

    def run_id():
        nonlocal counter
        counter += 1
        return f"run-{counter}"

    orchestrator = FleetClockOrchestrator(
        _FakeHass(), manager, _config(), run_id_factory=run_id
    )
    for _ in range(21):
        await _finish_after_start(orchestrator)

    assert len(orchestrator.history) == 20
    assert orchestrator.history[0]["run_id"] == "run-2"
    assert orchestrator.history[-1]["run_id"] == "run-21"
