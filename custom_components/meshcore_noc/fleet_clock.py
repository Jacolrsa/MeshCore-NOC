"""Serialized fleet orchestration for Clock Intelligence Phase 2."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .clock import (
    ClockCheckState,
    ClockTarget,
    MeshCoreNocClockManager,
)
from .const import FLEET_CLOCK_HISTORY_LIMIT


class FleetClockError(HomeAssistantError):
    """Base error for fleet clock orchestration."""


class FleetClockAlreadyRunningError(FleetClockError):
    """A fleet run already owns the serialized queue."""


class FleetClockNotRunningError(FleetClockError):
    """There is no active fleet run to cancel."""


class FleetClockState(StrEnum):
    """Observable fleet-run lifecycle."""

    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting_between_repeaters"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class FleetClockTrigger(StrEnum):
    """Fleet-run origin."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class FleetClockConfig:
    """Runtime fleet timing and scheduling options."""

    automatic_enabled: bool
    interval_hours: int
    success_delay_seconds: int
    failure_delay_seconds: int
    rotating_start: bool

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics-safe configuration."""
        return {
            "automatic_enabled": self.automatic_enabled,
            "interval_hours": self.interval_hours,
            "success_delay_seconds": self.success_delay_seconds,
            "failure_delay_seconds": self.failure_delay_seconds,
            "rotating_start": self.rotating_start,
        }


@dataclass(slots=True)
class FleetRun:
    """Mutable current fleet-run state."""

    run_id: str
    trigger: FleetClockTrigger
    state: FleetClockState
    ordered_stable_ids: tuple[str, ...]
    ordered_labels: tuple[str, ...]
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_index: int = 0
    current_stable_id: str | None = None
    current_friendly_name: str | None = None
    completed_count: int = 0
    success_count: int = 0
    timeout_count: int = 0
    failure_count: int = 0
    next_check_at: datetime | None = None
    cancellation_requested: bool = False
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def total_repeaters(self) -> int:
        """Return immutable snapshot size."""
        return len(self.ordered_stable_ids)

    @property
    def remaining_count(self) -> int:
        """Return targets not yet completed."""
        return max(0, self.total_repeaters - self.completed_count)

    def as_dict(self) -> dict[str, Any]:
        """Return complete fleet state and summary."""
        duration = (
            (self.completed_at - self.started_at).total_seconds()
            if self.started_at is not None and self.completed_at is not None
            else None
        )
        return {
            "run_id": self.run_id,
            "trigger": self.trigger,
            "state": self.state,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_repeaters": self.total_repeaters,
            "current_index": self.current_index,
            "current_stable_id": self.current_stable_id,
            "current_friendly_name": self.current_friendly_name,
            "completed_count": self.completed_count,
            "success_count": self.success_count,
            "timeout_count": self.timeout_count,
            "failure_count": self.failure_count,
            "remaining_count": self.remaining_count,
            "next_check_at": self.next_check_at,
            "cancellation_requested": self.cancellation_requested,
            "ordered_repeaters": [
                {"stable_id": stable_id, "friendly_name": label}
                for stable_id, label in zip(
                    self.ordered_stable_ids, self.ordered_labels, strict=True
                )
            ],
            "outcomes": list(self.outcomes),
            "total_duration_seconds": duration,
            "cancelled": self.state is FleetClockState.CANCELLED,
            "error": self.error,
        }


DelayWaiter = Callable[[float, asyncio.Event], Awaitable[bool]]
ScheduleAt = Callable[[datetime, Callable[[datetime], None]], Callable[[], None]]


async def _async_wait_for_delay(seconds: float, cancel_event: asyncio.Event) -> bool:
    """Wait for a delay or return early when cancellation is requested."""
    if seconds <= 0:
        return cancel_event.is_set()
    try:
        async with asyncio.timeout(seconds):
            await cancel_event.wait()
    except TimeoutError:
        return False
    return True


class FleetClockOrchestrator:
    """Run managed clock checks through one serialized queue."""

    def __init__(
        self,
        hass: HomeAssistant,
        clock_manager: MeshCoreNocClockManager,
        config: FleetClockConfig,
        *,
        now: Callable[[], datetime] = dt_util.utcnow,
        monotonic_time: Callable[[], float] = monotonic,
        delay_waiter: DelayWaiter = _async_wait_for_delay,
        schedule_at: ScheduleAt | None = None,
        run_id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        """Initialize without starting a run or scheduler."""
        self.hass = hass
        self.clock_manager = clock_manager
        self.config = config
        self._now = now
        self._monotonic = monotonic_time
        self._delay_waiter = delay_waiter
        self._schedule_at = schedule_at or self._async_schedule_at
        self._run_id_factory = run_id_factory
        self._current_run: FleetRun | None = None
        self._task: asyncio.Task[None] | None = None
        self._cancel_event = asyncio.Event()
        self._listeners: list[Callable[[], None]] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=FLEET_CLOCK_HISTORY_LIMIT)
        self._rotation_index = 0
        self._unsub_scheduler: Callable[[], None] | None = None
        self.next_scheduled_run: datetime | None = None
        self.scheduler_state = "disabled"
        self.scheduled_runs_skipped = 0
        self._stopped = False

    @property
    def current_run(self) -> dict[str, Any] | None:
        """Return current or most recently completed run state."""
        return self._current_run.as_dict() if self._current_run else None

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return the bounded last-20 fleet summaries."""
        return list(self._history)

    @property
    def last_summary(self) -> dict[str, Any] | None:
        """Return the latest terminal fleet summary."""
        return self._history[-1] if self._history else None

    @property
    def is_active(self) -> bool:
        """Return whether one run owns the queue."""
        return self._current_run is not None and self._current_run.state in {
            FleetClockState.QUEUED,
            FleetClockState.RUNNING,
            FleetClockState.WAITING,
            FleetClockState.CANCELLING,
        }

    @property
    def queue(self) -> list[str]:
        """Return remaining stable IDs in dispatch order."""
        run = self._current_run
        if run is None or not self.is_active:
            return []
        return list(run.ordered_stable_ids[run.completed_count :])

    @property
    def progress(self) -> str:
        """Return fleet progress for the diagnostic sensor."""
        run = self._current_run
        return f"{run.completed_count}/{run.total_repeaters}" if run else "0/0"

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe a fleet-level entity."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    def async_start_scheduler(self) -> None:
        """Schedule the first automatic run after the configured interval."""
        if self._stopped or not self.config.automatic_enabled:
            self.scheduler_state = "disabled"
            self.next_scheduled_run = None
            self._notify()
            return
        self._schedule_next()

    def _schedule_next(self) -> None:
        """Replace the next automatic callback deterministically."""
        if self._unsub_scheduler is not None:
            self._unsub_scheduler()
        next_run = self._utc_now() + timedelta(hours=self.config.interval_hours)
        self.next_scheduled_run = next_run
        self.scheduler_state = "scheduled"
        self._unsub_scheduler = self._schedule_at(
            next_run, self._async_scheduled_callback
        )
        self._notify()

    def _async_schedule_at(
        self, when: datetime, action: Callable[[datetime], None]
    ) -> Callable[[], None]:
        """Use Home Assistant's public point-in-time scheduler."""
        return async_track_point_in_utc_time(self.hass, action, when)

    @callback
    def _async_scheduled_callback(self, _now: datetime) -> None:
        """Start or skip one due scheduled run, then schedule the next."""
        self._unsub_scheduler = None
        self.next_scheduled_run = None
        if self.is_active:
            self.scheduled_runs_skipped += 1
        else:
            try:
                self.async_start_run(FleetClockTrigger.SCHEDULED)
            except FleetClockAlreadyRunningError:
                self.scheduled_runs_skipped += 1
        if not self._stopped and self.config.automatic_enabled:
            self._schedule_next()

    def async_start_run(
        self, trigger: FleetClockTrigger = FleetClockTrigger.MANUAL
    ) -> dict[str, Any]:
        """Snapshot addressable targets and start one background fleet run."""
        if self.is_active:
            run_id = self._current_run.run_id if self._current_run else "unknown"
            raise FleetClockAlreadyRunningError(
                f"Fleet clock run {run_id} is already active"
            )
        if self.clock_manager.outstanding_requests:
            raise FleetClockAlreadyRunningError(
                "A single-repeater clock check is already active"
            )
        if getattr(self.clock_manager, "sync_in_progress", False):
            raise FleetClockAlreadyRunningError(
                "A clock synchronization is already active"
            )
        targets = list(self.clock_manager.targets.values())
        if self.config.rotating_start and targets:
            start = self._rotation_index % len(targets)
            targets = targets[start:] + targets[:start]
        run = FleetRun(
            run_id=self._run_id_factory(),
            trigger=trigger,
            state=FleetClockState.QUEUED,
            ordered_stable_ids=tuple(target.stable_id for target in targets),
            ordered_labels=tuple(target.label for target in targets),
            queued_at=self._utc_now(),
        )
        self.clock_manager.reserve_fleet_targets(run.run_id, run.ordered_stable_ids)
        self._cancel_event = asyncio.Event()
        self._current_run = run
        self._task = self.hass.async_create_task(
            self._async_run(run, {target.stable_id: target for target in targets}),
            f"MeshCore NOC fleet clock run {run.run_id}",
        )
        self._notify()
        return run.as_dict()

    def async_cancel_run(self) -> dict[str, Any]:
        """Request a cooperative stop before the next dispatch."""
        if not self.is_active or self._current_run is None:
            raise FleetClockNotRunningError("No fleet clock run is active")
        self._current_run.cancellation_requested = True
        self._current_run.state = FleetClockState.CANCELLING
        self._current_run.next_check_at = None
        self._cancel_event.set()
        self._notify()
        return self._current_run.as_dict()

    async def _async_run(
        self, run: FleetRun, targets: Mapping[str, ClockTarget]
    ) -> None:
        """Process exactly one target at a time until terminal."""
        run.started_at = self._utc_now()
        run.state = FleetClockState.RUNNING
        self._notify()
        try:
            if not run.ordered_stable_ids:
                run.state = FleetClockState.FAILED
                run.error = "No managed addressable repeaters are available"
                return
            for index, stable_id in enumerate(run.ordered_stable_ids, start=1):
                if run.cancellation_requested:
                    run.state = FleetClockState.CANCELLED
                    break
                target = targets[stable_id]
                run.state = FleetClockState.RUNNING
                run.current_index = index
                run.current_stable_id = stable_id
                run.current_friendly_name = target.label
                run.next_check_at = None
                self._notify()
                outcome = await self._async_check_one(run, target)
                run.outcomes.append(outcome)
                run.completed_count += 1
                outcome_state = outcome["state"]
                if outcome_state == ClockCheckState.COMPLETED:
                    run.success_count += 1
                    delay = self.config.success_delay_seconds
                elif outcome_state == ClockCheckState.TIMED_OUT:
                    run.timeout_count += 1
                    delay = self.config.failure_delay_seconds
                else:
                    run.failure_count += 1
                    delay = self.config.failure_delay_seconds
                self._notify()
                if run.cancellation_requested:
                    run.state = FleetClockState.CANCELLED
                    break
                if index < run.total_repeaters:
                    run.state = FleetClockState.WAITING
                    run.next_check_at = self._utc_now() + timedelta(seconds=delay)
                    self._notify()
                    cancelled = await self._delay_waiter(delay, self._cancel_event)
                    run.next_check_at = None
                    if cancelled or run.cancellation_requested:
                        run.state = FleetClockState.CANCELLED
                        break
            else:
                run.state = (
                    FleetClockState.COMPLETED
                    if run.failure_count == 0 and run.timeout_count == 0
                    else FleetClockState.COMPLETED_WITH_ERRORS
                )
        except asyncio.CancelledError:
            run.cancellation_requested = True
            run.state = FleetClockState.CANCELLED
            raise
        except Exception as err:  # noqa: BLE001 - orchestration boundary
            run.state = FleetClockState.FAILED
            run.error = str(err)
        finally:
            run.completed_at = self._utc_now()
            run.next_check_at = None
            self.clock_manager.release_fleet_targets(run.run_id)
            summary = run.as_dict()
            self._history.append(summary)
            if (
                self.config.rotating_start
                and run.state
                in {
                    FleetClockState.COMPLETED,
                    FleetClockState.COMPLETED_WITH_ERRORS,
                }
                and run.total_repeaters
            ):
                self._rotation_index = (self._rotation_index + 1) % run.total_repeaters
            self._notify()

    async def _async_check_one(
        self, run: FleetRun, target: ClockTarget
    ) -> dict[str, Any]:
        """Return one bounded per-repeater outcome without stopping the fleet."""
        started_at = self._utc_now()
        started_monotonic = self._monotonic()
        try:
            result = await self.clock_manager.async_check_clock(
                target.stable_id, fleet_run_id=run.run_id
            )
            state = result.state
            return {
                "stable_id": target.stable_id,
                "friendly_name": target.label,
                "state": state,
                "started_at": started_at,
                "completed_at": self._utc_now(),
                "duration_seconds": max(0, self._monotonic() - started_monotonic),
                "clock_offset_seconds": result.clock_offset_seconds,
                "clock_status": result.clock_status,
                "error": result.error,
            }
        except Exception as err:  # noqa: BLE001 - isolate one queue item
            return {
                "stable_id": target.stable_id,
                "friendly_name": target.label,
                "state": ClockCheckState.FAILED,
                "started_at": started_at,
                "completed_at": self._utc_now(),
                "duration_seconds": max(0, self._monotonic() - started_monotonic),
                "clock_offset_seconds": None,
                "clock_status": None,
                "error": str(err),
            }

    @callback
    def async_stop(self) -> None:
        """Cancel scheduler, delay, and active orchestration task on unload."""
        self._stopped = True
        if self._unsub_scheduler is not None:
            self._unsub_scheduler()
            self._unsub_scheduler = None
        self.next_scheduled_run = None
        self.scheduler_state = "stopped"
        self._cancel_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        if self._current_run is not None:
            self.clock_manager.release_fleet_targets(self._current_run.run_id)
        self._notify()

    def _utc_now(self) -> datetime:
        now = self._now()
        return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
