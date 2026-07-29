"""Serialized fleet clock synchronization and scheduling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .clock import ClockSyncResult, ClockSyncState, MeshCoreNocClockManager

_STORAGE_VERSION = 1


class FleetClockSyncError(HomeAssistantError):
    """Base error for fleet clock synchronization."""


class FleetClockSyncAlreadyRunningError(FleetClockSyncError):
    """A clock operation already owns the synchronization queue."""


class FleetClockSyncState(StrEnum):
    """Observable fleet synchronization lifecycle."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting_between_repeaters"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    CANCELLED = "cancelled"
    FAILED = "failed"


class FleetClockSyncTrigger(StrEnum):
    """Fleet synchronization origin."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"


@dataclass(frozen=True, slots=True)
class FleetClockSyncConfig:
    """Runtime scheduling and network-pacing configuration."""

    automatic_enabled: bool
    interval_hours: int
    inter_repeater_delay_seconds: int

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics-safe configuration."""
        return {
            "automatic_enabled": self.automatic_enabled,
            "interval_hours": self.interval_hours,
            "inter_repeater_delay_seconds": self.inter_repeater_delay_seconds,
        }


@dataclass(slots=True)
class FleetClockSyncRun:
    """Mutable state for one serialized synchronization run."""

    run_id: str
    trigger: FleetClockSyncTrigger
    state: FleetClockSyncState
    started_at: datetime
    total_repeaters: int
    completed_at: datetime | None = None
    current_repeater: str | None = None
    completed_count: int = 0
    successful: int = 0
    already_ahead: int = 0
    failed: int = 0
    skipped: int = 0
    per_repeater: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the stable fleet service and entity contract."""
        duration = (
            max(0.0, (self.completed_at - self.started_at).total_seconds())
            if self.completed_at is not None
            else None
        )
        return {
            "run_id": self.run_id,
            "trigger": self.trigger,
            "state": self.state,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": duration,
            "total_repeaters": self.total_repeaters,
            "current_repeater": self.current_repeater,
            "completed_count": self.completed_count,
            "successful": self.successful,
            "already_ahead": self.already_ahead,
            "failed": self.failed,
            "skipped": self.skipped,
            "per_repeater": list(self.per_repeater),
            "error": self.error,
        }


class FleetSyncStore(Protocol):
    """Minimal Home Assistant Store contract used for deterministic tests."""

    async def async_load(self) -> dict[str, Any] | None:
        """Load retained state."""

    async def async_save(self, data: dict[str, Any]) -> None:
        """Persist retained state."""


DelayWaiter = Callable[[float, asyncio.Event], Awaitable[bool]]
ScheduleAt = Callable[[datetime, Callable[[datetime], None]], Callable[[], None]]


async def _async_wait_for_delay(seconds: float, cancel_event: asyncio.Event) -> bool:
    """Wait for pacing delay, returning early after cancellation."""
    if seconds <= 0:
        return cancel_event.is_set()
    try:
        async with asyncio.timeout(seconds):
            await cancel_event.wait()
    except TimeoutError:
        return False
    return True


def _serialize(value: Any) -> Any:
    """Convert retained datetimes and enums into JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _parse_datetime(value: Any) -> datetime | None:
    """Return one normalized UTC datetime from retained storage."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


class FleetClockSyncOrchestrator:
    """Synchronize every managed addressable repeater through one safe queue."""

    def __init__(
        self,
        hass: HomeAssistant,
        clock_manager: MeshCoreNocClockManager,
        config: FleetClockSyncConfig,
        *,
        storage_key: str,
        store: FleetSyncStore | None = None,
        now: Callable[[], datetime] = dt_util.utcnow,
        monotonic_time: Callable[[], float] = monotonic,
        delay_waiter: DelayWaiter = _async_wait_for_delay,
        schedule_at: ScheduleAt | None = None,
        run_id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        """Initialize without restoring state or starting timers."""
        self.hass = hass
        self.clock_manager = clock_manager
        self.config = config
        self._store = store or Store(hass, _STORAGE_VERSION, storage_key)
        self._now = now
        self._monotonic = monotonic_time
        self._delay_waiter = delay_waiter
        self._schedule_at = schedule_at or self._async_schedule_at
        self._run_id_factory = run_id_factory
        self._current_run: FleetClockSyncRun | None = None
        self._last_summary: dict[str, Any] | None = None
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._cancel_event = asyncio.Event()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_scheduler: Callable[[], None] | None = None
        self.next_automatic_sync: datetime | None = None
        self._restored_due: datetime | None = None
        self._stopped = False

    @property
    def is_active(self) -> bool:
        """Return whether one fleet synchronization owns the queue."""
        return self._current_run is not None and self._current_run.state in {
            FleetClockSyncState.RUNNING,
            FleetClockSyncState.WAITING,
        }

    @property
    def current_run(self) -> dict[str, Any] | None:
        """Return current or most recent in-memory state."""
        return self._current_run.as_dict() if self._current_run else None

    @property
    def last_summary(self) -> dict[str, Any] | None:
        """Return the latest terminal summary, including restored state."""
        return self._last_summary

    @property
    def state_attributes(self) -> dict[str, Any]:
        """Expose the complete stable dashboard/entity contract."""
        run = self.current_run
        last = self.last_summary or {}
        return {
            "fleet_sync_running": self.is_active,
            "fleet_sync_current_repeater": (
                run.get("current_repeater") if run else None
            ),
            "fleet_sync_completed_count": (run.get("completed_count", 0) if run else 0),
            "fleet_sync_total_count": (run.get("total_repeaters", 0) if run else 0),
            "last_fleet_sync_result": last.get("state"),
            "last_fleet_sync_started_at": last.get("started_at"),
            "last_fleet_sync_completed_at": last.get("completed_at"),
            "last_fleet_sync_duration_seconds": last.get("duration_seconds"),
            "last_fleet_sync_successful": last.get("successful", 0),
            "last_fleet_sync_already_ahead": last.get("already_ahead", 0),
            "last_fleet_sync_failed": last.get("failed", 0),
            "last_fleet_sync_trigger": last.get("trigger"),
            "automatic_sync_enabled": self.config.automatic_enabled,
            "automatic_sync_interval": self.config.interval_hours,
            "next_automatic_sync": self.next_automatic_sync,
            "current_run": run,
            "last_summary": self.last_summary,
        }

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe a fleet synchronization entity."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    async def async_initialize(self) -> None:
        """Restore useful terminal state without restoring stale activity."""
        retained = await self._store.async_load()
        if not isinstance(retained, dict):
            return
        summary = retained.get("last_summary")
        if isinstance(summary, dict):
            restored = dict(summary)
            for key in ("started_at", "completed_at"):
                restored[key] = _parse_datetime(restored.get(key))
            self._last_summary = restored
        if retained.get("interval_hours") == self.config.interval_hours:
            self._restored_due = _parse_datetime(retained.get("next_automatic_sync"))

    def async_start_scheduler(self) -> None:
        """Restore or create exactly one automatic synchronization timer."""
        if self._stopped or not self.config.automatic_enabled:
            self.next_automatic_sync = None
            self._restored_due = None
            self._notify()
            self._save_later()
            return
        due = self._restored_due or (
            self._utc_now() + timedelta(hours=self.config.interval_hours)
        )
        self._restored_due = None
        self._schedule(due)

    def _schedule(self, when: datetime) -> None:
        """Replace the automatic timer and retain the exact due time."""
        if self._unsub_scheduler is not None:
            self._unsub_scheduler()
        self.next_automatic_sync = when
        self._unsub_scheduler = self._schedule_at(when, self._async_scheduled_callback)
        self._notify()
        self._save_later()

    def _async_schedule_at(
        self, when: datetime, action: Callable[[datetime], None]
    ) -> Callable[[], None]:
        """Use Home Assistant's public UTC scheduler."""
        return async_track_point_in_utc_time(self.hass, action, when)

    @callback
    def _async_scheduled_callback(self, _now: datetime) -> None:
        """Run one overdue interval at most, then schedule from current time."""
        self._unsub_scheduler = None
        self.next_automatic_sync = None
        if not self._stopped and not self.is_active:
            try:
                self._start_background(FleetClockSyncTrigger.AUTOMATIC)
            except FleetClockSyncAlreadyRunningError:
                pass
        if not self._stopped and self.config.automatic_enabled:
            self._schedule(
                self._utc_now() + timedelta(hours=self.config.interval_hours)
            )

    async def async_sync_all(
        self, trigger: FleetClockSyncTrigger = FleetClockSyncTrigger.MANUAL
    ) -> dict[str, Any]:
        """Run one fleet synchronization and return its terminal response."""
        task = asyncio.current_task()
        return await self._async_execute(trigger, task)

    def _start_background(self, trigger: FleetClockSyncTrigger) -> None:
        """Start the same fleet path for automatic scheduling."""
        if (
            self.is_active
            or self.clock_manager.check_in_progress
            or self.clock_manager.sync_in_progress
        ):
            raise FleetClockSyncAlreadyRunningError(
                "Another clock operation is already running"
            )
        task = self.hass.async_create_task(
            self._async_execute(trigger),
            "MeshCore NOC automatic fleet clock synchronization",
        )
        self._task = task

    async def _async_execute(
        self,
        trigger: FleetClockSyncTrigger,
        owner_task: asyncio.Task[Any] | None = None,
    ) -> dict[str, Any]:
        """Process a snapshot of managed targets sequentially."""
        if self.is_active:
            raise FleetClockSyncAlreadyRunningError(
                "A fleet clock synchronization is already running"
            )
        run_id = self._run_id_factory()
        try:
            self.clock_manager.begin_fleet_sync(run_id)
        except HomeAssistantError as err:
            raise FleetClockSyncAlreadyRunningError(str(err)) from err
        targets = list(self.clock_manager.targets.values())
        run = FleetClockSyncRun(
            run_id=run_id,
            trigger=trigger,
            state=FleetClockSyncState.RUNNING,
            started_at=self._utc_now(),
            total_repeaters=len(targets),
        )
        self._current_run = run
        self._cancel_event = asyncio.Event()
        if owner_task is not None:
            self._task = owner_task
        self._notify()
        try:
            if not targets:
                run.state = FleetClockSyncState.FAILED
                run.error = "No managed addressable repeaters are available"
            else:
                for index, target in enumerate(targets):
                    if self._cancel_event.is_set():
                        run.state = FleetClockSyncState.CANCELLED
                        break
                    run.state = FleetClockSyncState.RUNNING
                    run.current_repeater = target.label
                    self._notify()
                    result = await self.clock_manager.async_sync_repeater_clock(
                        target.stable_id,
                        fleet_sync_run_id=run_id,
                    )
                    outcome = self._result_for(target.label, result)
                    run.per_repeater.append(outcome)
                    run.completed_count += 1
                    if result.result is ClockSyncState.SUCCESS:
                        run.successful += 1
                    elif result.result is ClockSyncState.ALREADY_AHEAD:
                        run.already_ahead += 1
                    elif result.result is ClockSyncState.CANCELLED:
                        run.skipped += 1
                    else:
                        run.failed += 1
                    self._notify()
                    if self._cancel_event.is_set():
                        run.state = FleetClockSyncState.CANCELLED
                        break
                    if index < len(targets) - 1:
                        run.state = FleetClockSyncState.WAITING
                        self._notify()
                        cancelled = await self._delay_waiter(
                            self.config.inter_repeater_delay_seconds,
                            self._cancel_event,
                        )
                        if cancelled:
                            run.state = FleetClockSyncState.CANCELLED
                            break
                else:
                    run.state = (
                        FleetClockSyncState.COMPLETED
                        if run.failed == 0
                        else FleetClockSyncState.COMPLETED_WITH_ERRORS
                    )
        except asyncio.CancelledError:
            run.state = FleetClockSyncState.CANCELLED
            run.error = "fleet synchronization cancelled"
        except Exception as err:  # noqa: BLE001 - orchestration boundary
            run.state = FleetClockSyncState.FAILED
            run.error = str(err)
        finally:
            run.completed_at = self._utc_now()
            run.current_repeater = None
            self.clock_manager.end_fleet_sync(run_id)
            self._last_summary = run.as_dict()
            if self._task is asyncio.current_task():
                self._task = None
            self._notify()
            await self._async_save()
        return run.as_dict()

    @staticmethod
    def _result_for(friendly_name: str, result: ClockSyncResult) -> dict[str, Any]:
        """Map one single-target result into the stable fleet contract."""
        return {
            "stable_id": result.stable_id,
            "friendly_name": friendly_name,
            "result": result.result,
            "offset_before_sync_seconds": result.pre_sync_offset_seconds,
            "offset_after_sync_seconds": result.post_sync_offset_seconds,
            "duration_seconds": result.duration_seconds,
            "remote_response": result.remote_response_text,
            "error": result.error,
        }

    @callback
    def async_stop(self) -> None:
        """Remove timers and cancel any current fleet operation."""
        self._stopped = True
        if self._unsub_scheduler is not None:
            self._unsub_scheduler()
            self._unsub_scheduler = None
        self.next_automatic_sync = None
        self._cancel_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.clock_manager.end_fleet_sync()
        self._notify()

    async def _async_save(self) -> None:
        """Persist only useful terminal state and the next due interval."""
        await self._store.async_save(
            _serialize(
                {
                    "last_summary": self._last_summary,
                    "next_automatic_sync": self.next_automatic_sync,
                    "interval_hours": self.config.interval_hours,
                }
            )
        )

    def _save_later(self) -> None:
        """Persist scheduler changes without blocking callbacks."""
        if self._stopped:
            return
        self.hass.async_create_task(
            self._async_save(),
            "Persist MeshCore NOC fleet clock synchronization state",
        )

    def _utc_now(self) -> datetime:
        now = self._now()
        return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
