"""Tests for serialized fleet clock synchronization and scheduling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.meshcore_noc.clock import (
    ClockSyncResult,
    ClockSyncState,
    ClockTarget,
)
from custom_components.meshcore_noc.fleet_sync import (
    FleetClockSyncAlreadyRunningError,
    FleetClockSyncConfig,
    FleetClockSyncOrchestrator,
    FleetClockSyncTrigger,
)


class _Store:
    def __init__(self, retained=None):
        self.retained = retained
        self.saved = []

    async def async_load(self):
        return self.retained

    async def async_save(self, data):
        self.saved.append(data)


class _Hass:
    def async_create_task(self, coro, _name):
        return asyncio.create_task(coro)


class _Manager:
    def __init__(self):
        self.targets = {
            "laguna": ClockTarget("laguna", "01c1a4fa32c6", "entry", "Laguna2"),
            "aurora": ClockTarget("aurora", "112233445566", "entry", "Aurora"),
            "saldanha": ClockTarget("saldanha", "223344556677", "entry", "Saldanha"),
        }
        self.calls = []
        self.fleet_run = None
        self.check_in_progress = False
        self.sync_in_progress = False
        self.failed = set()

    def begin_fleet_sync(self, run_id):
        if self.check_in_progress or self.sync_in_progress:
            raise HomeAssistantError("Another clock operation is already running")
        self.fleet_run = run_id

    def end_fleet_sync(self, run_id=None):
        if run_id is None or run_id == self.fleet_run:
            self.fleet_run = None

    async def async_sync_repeater_clock(self, stable_id, *, fleet_sync_run_id):
        assert fleet_sync_run_id == self.fleet_run
        self.calls.append(stable_id)
        state = (
            ClockSyncState.FAILED
            if stable_id in self.failed
            else ClockSyncState.SUCCESS
        )
        return ClockSyncResult(
            stable_id=stable_id,
            pubkey_prefix=self.targets[stable_id].pubkey_prefix,
            result=state,
            started_at=datetime(2026, 7, 29, tzinfo=UTC),
            completed_at=datetime(2026, 7, 29, 0, 0, 1, tzinfo=UTC),
            duration_seconds=1,
            pre_sync_offset_seconds=-120,
            post_sync_offset_seconds=1 if state is ClockSyncState.SUCCESS else None,
            remote_response_text="OK" if state is ClockSyncState.SUCCESS else None,
            error="rejected" if state is ClockSyncState.FAILED else None,
        )


def _orchestrator(
    manager=None, *, config=None, store=None, now=None, delay=None, schedule=None
):
    manager = manager or _Manager()
    return FleetClockSyncOrchestrator(
        _Hass(),
        manager,
        config or FleetClockSyncConfig(False, 24, 2),
        storage_key="test",
        store=store or _Store(),
        now=now or (lambda: datetime(2026, 7, 29, tzinfo=UTC)),
        delay_waiter=delay or (lambda _seconds, _event: asyncio.sleep(0, result=False)),
        schedule_at=schedule,
        run_id_factory=lambda: "fleet-run",
    )


async def test_fleet_sync_is_sequential_paced_and_continues_after_failure():
    manager = _Manager()
    manager.failed.add("aurora")
    delays = []

    async def wait(seconds, _event):
        delays.append(seconds)
        return False

    result = await _orchestrator(manager, delay=wait).async_sync_all()

    assert manager.calls == ["laguna", "aurora", "saldanha"]
    assert delays == [2, 2]
    assert result["total_repeaters"] == 3
    assert result["successful"] == 2
    assert result["failed"] == 1
    assert result["trigger"] == "manual"
    assert result["state"] == "completed_with_errors"
    assert [item["stable_id"] for item in result["per_repeater"]] == manager.calls
    assert result["per_repeater"][0]["remote_response"] == "OK"


async def test_fleet_sync_rejects_concurrent_clock_operation():
    manager = _Manager()
    manager.sync_in_progress = True

    with pytest.raises(FleetClockSyncAlreadyRunningError):
        await _orchestrator(manager).async_sync_all()


async def test_automatic_schedule_restores_one_overdue_run():
    now = datetime(2026, 7, 29, tzinfo=UTC)
    callbacks = []
    store = _Store(
        {
            "interval_hours": 24,
            "next_automatic_sync": (now - timedelta(hours=3)).isoformat(),
        }
    )

    def schedule(when, callback):
        callbacks.append((when, callback))
        return lambda: None

    manager = _Manager()
    orchestrator = _orchestrator(
        manager,
        config=FleetClockSyncConfig(True, 24, 0),
        store=store,
        now=lambda: now,
        schedule=schedule,
    )
    await orchestrator.async_initialize()
    orchestrator.async_start_scheduler()
    assert callbacks[0][0] < now
    callbacks[0][1](now)
    task = orchestrator._task
    assert task is not None
    await task
    assert manager.calls == ["laguna", "aurora", "saldanha"]
    assert len(callbacks) == 2
    assert callbacks[1][0] == now + timedelta(hours=24)
    assert orchestrator.last_summary["trigger"] is FleetClockSyncTrigger.AUTOMATIC


@pytest.mark.parametrize("hours", [6, 12, 24, 72, 168])
async def test_each_automatic_interval_schedules_from_now(hours):
    now = datetime(2026, 7, 29, tzinfo=UTC)
    scheduled = []
    orchestrator = _orchestrator(
        config=FleetClockSyncConfig(True, hours, 2),
        now=lambda: now,
        schedule=lambda when, _callback: scheduled.append(when) or (lambda: None),
    )
    await orchestrator.async_initialize()
    orchestrator.async_start_scheduler()
    assert scheduled == [now + timedelta(hours=hours)]


async def test_automatic_sync_is_disabled_by_default():
    orchestrator = _orchestrator()
    await orchestrator.async_initialize()
    orchestrator.async_start_scheduler()
    assert orchestrator.next_automatic_sync is None
    assert orchestrator.state_attributes["automatic_sync_enabled"] is False


async def test_options_interval_change_discards_old_due_time():
    now = datetime(2026, 7, 29, tzinfo=UTC)
    scheduled = []
    store = _Store(
        {
            "interval_hours": 6,
            "next_automatic_sync": (now + timedelta(hours=1)).isoformat(),
        }
    )
    orchestrator = _orchestrator(
        config=FleetClockSyncConfig(True, 12, 2),
        store=store,
        now=lambda: now,
        schedule=lambda when, _callback: scheduled.append(when) or (lambda: None),
    )
    await orchestrator.async_initialize()
    orchestrator.async_start_scheduler()
    assert scheduled == [now + timedelta(hours=12)]


async def test_unload_cancels_active_fleet_sync_and_releases_gate():
    manager = _Manager()
    started = asyncio.Event()

    async def blocked_sync(stable_id, *, fleet_sync_run_id):
        started.set()
        await asyncio.Event().wait()

    manager.async_sync_repeater_clock = blocked_sync
    orchestrator = _orchestrator(manager)
    task = asyncio.create_task(orchestrator.async_sync_all())
    await started.wait()
    orchestrator.async_stop()
    result = await task
    assert result["state"] == "cancelled"
    assert manager.fleet_run is None
