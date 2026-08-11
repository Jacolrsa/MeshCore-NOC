"""Event-driven manual clock intelligence for managed MeshCore repeaters."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.util import dt as dt_util

from .const import (
    CLOCK_HISTORY_LIMIT,
    CLOCK_RESPONSE_TIMEOUT,
    MESHCORE_DOMAIN,
    MESHCORE_RAW_EVENT,
)

_CLOCK_PATTERN = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*-\s*"
    r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})\s+UTC\s*$"
)
_CONTACT_MESSAGE_EVENT = "EventType.CONTACT_MSG_RECV"
_MAX_TEXT_TIMESTAMP_DIFFERENCE = 90
_LOGGER = logging.getLogger(__name__)


class ClockManagerError(HomeAssistantError):
    """Base error for a rejected manual clock check."""


class UnknownManagedRepeaterError(ClockManagerError):
    """The requested stable ID is not a managed repeater target."""


class ClockCheckInProgressError(ClockManagerError):
    """A request is already pending for this repeater."""


class ClockCheckCooldownError(ClockManagerError):
    """The repeater is still inside its manual-command cooldown."""


class ClockCheckFleetCollisionError(ClockManagerError):
    """A manual check targets a repeater reserved by the active fleet run."""


class ClockStatus(StrEnum):
    """Clock drift severity."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class ClockCheckState(StrEnum):
    """Observable lifecycle state for one manual check."""

    QUEUED = "queued"
    CALLING_SERVICE = "calling_service"
    SENT = "sent"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class ClockAttemptOutcome(StrEnum):
    """Latest completed clock-attempt outcome."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"
    MALFORMED = "malformed"


class ClockSyncState(StrEnum):
    """Stable service result for one repeater clock synchronization."""

    SUCCESS = "success"
    ALREADY_AHEAD = "already_ahead"
    TIMEOUT = "timeout"
    UNRESOLVED = "unresolved"
    UNAUTHORIZED = "unauthorized"
    COMMAND_FAILED = "command_failed"
    VERIFICATION_FAILED = "verification_failed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ClockTarget:
    """Public addressing data for one managed repeater."""

    stable_id: str
    pubkey_prefix: str
    meshcore_config_entry_id: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class NonAddressableRepeater:
    """Diagnostic evidence for one managed device excluded from clock targets."""

    stable_id: str
    friendly_name: str
    resolution_sources_checked: tuple[str, ...]
    rejection_reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return service-safe diagnostic data."""
        return {
            "stable_id": self.stable_id,
            "friendly_name": self.friendly_name,
            "resolution_sources_checked": list(self.resolution_sources_checked),
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, slots=True)
class ManagedRepeaterAddressability:
    """Complete acceptance evidence for one configured managed device."""

    stable_id: str
    friendly_name: str
    device_type: str
    resolution_source: str | None
    pubkey_prefix: str | None
    resolution_sources_checked: tuple[str, ...]
    accepted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return complete safe addressability diagnostics."""
        return {
            "stable_id": self.stable_id,
            "friendly_name": self.friendly_name,
            "device_type": self.device_type,
            "resolution_source": self.resolution_source,
            "pubkey_prefix": self.pubkey_prefix,
            "resolution_sources_checked": list(self.resolution_sources_checked),
            "accepted": self.accepted,
            "reason": self.reason,
        }


@dataclass(slots=True)
class ClockResult:
    """Latest clock state and request lifecycle for one repeater."""

    stable_id: str
    pubkey_prefix: str
    state: ClockCheckState = ClockCheckState.QUEUED
    last_clock_check: datetime | None = None
    last_clock_reply: datetime | None = None
    clock_offset_seconds: int | None = None
    clock_status: ClockStatus = ClockStatus.UNKNOWN
    clock_rtt_ms: int | None = None
    response_text: str | None = None
    sender_timestamp: int | None = None
    service_response: Any = None
    error: str | None = None
    last_successful_clock_check: datetime | None = None
    last_clock_attempt: datetime | None = None
    last_clock_attempt_outcome: ClockAttemptOutcome | None = None
    last_clock_attempt_error: str | None = None
    last_sync_result: ClockSyncState | None = None
    last_sync_time: datetime | None = None
    offset_before_sync_seconds: int | None = None
    offset_after_sync_seconds: int | None = None
    sync_duration_seconds: float | None = None
    last_sync_response: str | None = None
    last_sync_error: str | None = None
    sync_running: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a Home Assistant service-response-safe representation."""
        return {
            "stable_id": self.stable_id,
            "pubkey_prefix": self.pubkey_prefix,
            "state": self.state,
            "last_clock_check": self.last_clock_check,
            "last_clock_reply": self.last_clock_reply,
            "clock_offset_seconds": self.clock_offset_seconds,
            "clock_status": self.clock_status,
            "clock_rtt_ms": self.clock_rtt_ms,
            "response_text": self.response_text,
            "sender_timestamp": self.sender_timestamp,
            "service_response": self.service_response,
            "error": self.error,
            "last_successful_clock_check": self.last_successful_clock_check,
            "last_clock_attempt": self.last_clock_attempt,
            "last_clock_attempt_outcome": self.last_clock_attempt_outcome,
            "last_clock_attempt_error": self.last_clock_attempt_error,
            "last_sync_result": self.last_sync_result,
            "last_sync_time": self.last_sync_time,
            "offset_before_sync_seconds": self.offset_before_sync_seconds,
            "offset_after_sync_seconds": self.offset_after_sync_seconds,
            "sync_duration_seconds": self.sync_duration_seconds,
            "last_sync_response": self.last_sync_response,
            "last_sync_error": self.last_sync_error,
            "sync_running": self.sync_running,
        }


@dataclass(slots=True)
class ClockSyncResult:
    """Service response for one bounded repeater clock synchronization."""

    stable_id: str
    pubkey_prefix: str | None
    result: ClockSyncState
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    pre_sync_offset_seconds: int | None = None
    post_sync_offset_seconds: int | None = None
    remote_response_text: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a Home Assistant service-response-safe representation."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClockHistoryEntry:
    """Bounded audit record for one completed check attempt."""

    stable_id: str
    pubkey_prefix: str
    requested_at: datetime
    completed_at: datetime
    state: ClockCheckState
    response_text: str | None
    sender_timestamp: int | None
    clock_offset_seconds: int | None
    clock_status: ClockStatus
    clock_rtt_ms: int | None
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics-safe history data."""
        return asdict(self)


@dataclass(slots=True)
class _PendingClockRequest:
    target: ClockTarget
    requested_at: datetime
    started_monotonic: float
    future: asyncio.Future[ClockResult]


@dataclass(slots=True)
class _PendingClockSync:
    target: ClockTarget
    started_at: datetime
    future: asyncio.Future[str]


def parse_clock_text(text: str) -> datetime:
    """Parse the public MeshCore repeater clock response as UTC."""
    match = _CLOCK_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError("clock response does not match HH:MM - D/M/YYYY UTC")
    values = {key: int(value) for key, value in match.groupdict().items()}
    return datetime(
        values["year"],
        values["month"],
        values["day"],
        values["hour"],
        values["minute"],
        tzinfo=UTC,
    )


def calculate_clock_offset(sender_timestamp: int, received_at: datetime) -> int:
    """Return signed seconds: positive ahead, negative behind."""
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    return round(sender_timestamp - received_at.timestamp())


def classify_clock_status(
    offset_seconds: int | None,
    warning_seconds: int = 120,
    critical_seconds: int = 300,
) -> ClockStatus:
    """Classify absolute drift using the Phase 1 thresholds."""
    if offset_seconds is None:
        return ClockStatus.UNKNOWN
    absolute_offset = abs(offset_seconds)
    if absolute_offset <= 30:
        return ClockStatus.GREEN
    if absolute_offset <= warning_seconds:
        return ClockStatus.YELLOW
    if absolute_offset <= critical_seconds:
        return ClockStatus.ORANGE
    return ClockStatus.RED


def clock_status_label(status: ClockStatus) -> str:
    """Return the user-facing Clock Status sensor value."""
    return {
        ClockStatus.UNKNOWN: "Unknown",
        ClockStatus.GREEN: "In Sync",
        ClockStatus.YELLOW: "Minor Drift",
        ClockStatus.ORANGE: "Drift",
        ClockStatus.RED: "Critical",
    }[status]


class MeshCoreNocClockManager:
    """Issue and correlate manual clock checks using public HA interfaces."""

    def __init__(
        self,
        hass: HomeAssistant,
        targets: Mapping[str, ClockTarget],
        *,
        managed_repeaters: Mapping[str, str] | None = None,
        non_addressable_repeaters: tuple[NonAddressableRepeater, ...] = (),
        managed_repeater_addressability: tuple[ManagedRepeaterAddressability, ...] = (),
        cooldown_seconds: int,
        timeout_seconds: float = CLOCK_RESPONSE_TIMEOUT,
        now: Callable[[], datetime] = dt_util.utcnow,
        monotonic_time: Callable[[], float] = monotonic,
        clock_thresholds: Callable[[str], tuple[int, int]] | None = None,
    ) -> None:
        """Initialize without accessing MeshCore integration internals."""
        self.hass = hass
        self.targets = dict(targets)
        self.managed_repeaters = dict(managed_repeaters or targets)
        self.non_addressable_repeaters = non_addressable_repeaters
        self.managed_repeater_addressability = managed_repeater_addressability
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds
        self._now = now
        self._monotonic = monotonic_time
        self._clock_thresholds = clock_thresholds
        self._pending: dict[str, _PendingClockRequest] = {}
        self._pending_sync: dict[str, _PendingClockSync] = {}
        self._sync_tasks: set[asyncio.Task[Any]] = set()
        self._results = {
            stable_id: ClockResult(stable_id, target.pubkey_prefix)
            for stable_id, target in self.targets.items()
        }
        self._last_request_monotonic: dict[str, float] = {}
        self._history: deque[ClockHistoryEntry] = deque(maxlen=CLOCK_HISTORY_LIMIT)
        self._listeners: dict[str, list[Callable[[], None]]] = {}
        self._fleet_run_id: str | None = None
        self._fleet_reserved_ids: set[str] = set()
        self._fleet_sync_run_id: str | None = None
        self._unsub_raw_event: Callable[[], None] | None = None
        self.last_request: dict[str, Any] | None = None
        self.last_response: dict[str, Any] | None = None
        self.last_parse_result: dict[str, Any] | None = None
        self.last_timeout: dict[str, Any] | None = None

    @property
    def outstanding_requests(self) -> list[dict[str, Any]]:
        """Return diagnostics for active requests without exposing internals."""
        return [
            {
                "stable_id": pending.target.stable_id,
                "pubkey_prefix": pending.target.pubkey_prefix,
                "requested_at": pending.requested_at,
            }
            for pending in self._pending.values()
        ]

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return the rolling last-20 history."""
        return [entry.as_dict() for entry in self._history]

    @property
    def sync_in_progress(self) -> bool:
        """Return whether any single or fleet synchronization is active."""
        return bool(self._pending_sync) or self._fleet_sync_run_id is not None

    @property
    def fleet_sync_active(self) -> bool:
        """Return whether the fleet synchronization queue owns operations."""
        return self._fleet_sync_run_id is not None

    @property
    def check_in_progress(self) -> bool:
        """Return whether a single or fleet read-only check is active."""
        return bool(self._pending) or self._fleet_run_id is not None

    def result_for(self, stable_id: str) -> ClockResult | None:
        """Return current clock information for a managed target."""
        return self._results.get(stable_id)

    def clock_data_age_seconds(self, stable_id: str) -> int | None:
        """Return age of the retained successful reading."""
        result = self.result_for(stable_id)
        if result is None or result.last_successful_clock_check is None:
            return None
        return max(
            0,
            round(
                (self._utc_now() - result.last_successful_clock_check).total_seconds()
            ),
        )

    @property
    def fleet_health(self) -> dict[str, Any]:
        """Summarize retained clock health across addressable repeaters."""
        counts = {status: 0 for status in ClockStatus}
        names = {ClockStatus.ORANGE: [], ClockStatus.RED: []}
        for stable_id, result in self._results.items():
            counts[result.clock_status] += 1
            if result.clock_status in names:
                names[result.clock_status].append(self.targets[stable_id].label)
        return {
            "in_sync": counts[ClockStatus.GREEN],
            "minor_drift": counts[ClockStatus.YELLOW],
            "drift": counts[ClockStatus.ORANGE],
            "critical": counts[ClockStatus.RED],
            "unknown": counts[ClockStatus.UNKNOWN],
            "drift_repeaters": sorted(names[ClockStatus.ORANGE]),
            "critical_repeaters": sorted(names[ClockStatus.RED]),
        }

    def reserve_fleet_targets(self, run_id: str, stable_ids: tuple[str, ...]) -> None:
        """Reserve one immutable fleet snapshot against manual overlap."""
        if self.sync_in_progress:
            raise ClockCheckFleetCollisionError(
                "A clock synchronization is already active"
            )
        if self._fleet_run_id is not None:
            raise ClockCheckFleetCollisionError(
                f"Fleet clock run {self._fleet_run_id} already owns the queue"
            )
        self._fleet_run_id = run_id
        self._fleet_reserved_ids = set(stable_ids)

    def release_fleet_targets(self, run_id: str) -> None:
        """Release reservations owned by one completed fleet run."""
        if self._fleet_run_id == run_id:
            self._fleet_run_id = None
            self._fleet_reserved_ids.clear()

    def begin_fleet_sync(self, run_id: str) -> None:
        """Acquire the integration-wide clock-operation gate for fleet sync."""
        if self._fleet_sync_run_id is not None:
            raise ClockCheckFleetCollisionError(
                f"Fleet clock synchronization {self._fleet_sync_run_id} is active"
            )
        if self._fleet_run_id is not None:
            raise ClockCheckFleetCollisionError(
                f"Fleet clock check {self._fleet_run_id} is active"
            )
        if self._pending or self._pending_sync:
            raise ClockCheckFleetCollisionError(
                "A single-repeater clock operation is already active"
            )
        self._fleet_sync_run_id = run_id

    def end_fleet_sync(self, run_id: str | None = None) -> None:
        """Release the fleet synchronization operation gate."""
        if run_id is None or self._fleet_sync_run_id == run_id:
            self._fleet_sync_run_id = None

    def async_start(self) -> None:
        """Subscribe once to the public raw MeshCore event."""
        if self._unsub_raw_event is None:
            self._unsub_raw_event = self.hass.bus.async_listen(
                MESHCORE_RAW_EVENT, self._async_handle_raw_event
            )

    @callback
    def async_stop(self) -> None:
        """Unsubscribe and cancel all outstanding requests."""
        if self._unsub_raw_event is not None:
            self._unsub_raw_event()
            self._unsub_raw_event = None
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.cancel()
        self._pending.clear()
        for pending in self._pending_sync.values():
            if not pending.future.done():
                pending.future.cancel()
        self._pending_sync.clear()
        for task in tuple(self._sync_tasks):
            task.cancel()
        self._sync_tasks.clear()
        self._fleet_sync_run_id = None

    @callback
    def async_add_listener(
        self, stable_id: str, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Notify a managed repeater's entities after clock state changes."""
        listeners = self._listeners.setdefault(stable_id, [])
        listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in listeners:
                listeners.remove(listener)

        return remove_listener

    def resolve_target(self, supplied_identifier: str) -> ClockTarget:
        """Resolve a stable ID, or a unique exact-prefix compatibility value."""
        target = self.targets.get(supplied_identifier)
        if target is None:
            prefix_matches = [
                candidate
                for candidate in self.targets.values()
                if candidate.pubkey_prefix == supplied_identifier.lower()
            ]
            if len(prefix_matches) == 1:
                target = prefix_matches[0]
        if target is not None:
            _LOGGER.debug(
                "Clock target resolved: supplied_stable_id=%s "
                "managed_repeater=%s pubkey_prefix=%s",
                supplied_identifier,
                target.stable_id,
                target.pubkey_prefix,
            )
            return target

        managed = supplied_identifier in self.managed_repeaters
        addressable = supplied_identifier in self.targets
        valid = [
            f"{target.stable_id} ({target.label})"
            for target in sorted(self.targets.values(), key=lambda item: item.label)
        ]
        raise UnknownManagedRepeaterError(
            f"Invalid clock target {supplied_identifier!r}: managed={managed}, "
            f"addressable={addressable}. Valid managed addressable repeaters: "
            f"{valid or 'none'}"
        )

    async def async_check_clock(
        self,
        stable_id: str,
        *,
        fleet_run_id: str | None = None,
        sync_operation: bool = False,
        bypass_cooldown: bool = False,
    ) -> ClockResult:
        """Run one manual read-only clock check and await its public reply."""
        supplied_identifier = stable_id
        target = self.resolve_target(supplied_identifier)
        stable_id = target.stable_id
        if not sync_operation and self._fleet_sync_run_id is not None:
            raise ClockCheckFleetCollisionError(
                "A fleet clock synchronization is already active"
            )
        if not sync_operation and target.pubkey_prefix.lower() in self._pending_sync:
            raise ClockCheckInProgressError(
                f"A clock synchronization is already pending for {stable_id}"
            )
        if stable_id in self._fleet_reserved_ids and fleet_run_id != self._fleet_run_id:
            raise ClockCheckFleetCollisionError(
                f"{stable_id!r} is queued or running in fleet clock run "
                f"{self._fleet_run_id}"
            )
        prefix = target.pubkey_prefix.lower()
        if prefix in self._pending:
            raise ClockCheckInProgressError(
                f"A clock check is already pending for {stable_id}"
            )
        now_monotonic = self._monotonic()
        last_request = self._last_request_monotonic.get(prefix)
        if (
            not bypass_cooldown
            and last_request is not None
            and now_monotonic - last_request < self.cooldown_seconds
        ):
            remaining = self.cooldown_seconds - (now_monotonic - last_request)
            raise ClockCheckCooldownError(
                f"Clock check cooldown active for {stable_id}; "
                f"retry in {remaining:.0f} seconds"
            )

        requested_at = self._utc_now()
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
        future: asyncio.Future[ClockResult] = asyncio.get_running_loop().create_future()
        pending = _PendingClockRequest(
            target=target,
            requested_at=requested_at,
            started_monotonic=now_monotonic,
            future=future,
        )
        self._pending[prefix] = pending
        self._last_request_monotonic[prefix] = now_monotonic
        self.last_request = {
            "stable_id": stable_id,
            "pubkey_prefix": target.pubkey_prefix,
            "requested_at": requested_at,
            "command": "clock",
        }
        self._notify(stable_id)

        try:
            if not self.hass.services.has_service(MESHCORE_DOMAIN, "execute_command"):
                return self._finish_failure(
                    pending, "meshcore.execute_command unavailable"
                )

            result.state = ClockCheckState.CALLING_SERVICE
            self._notify(stable_id)
            try:
                command = f'send_cmd {target.pubkey_prefix} "clock"'
                _LOGGER.debug(
                    "Dispatching managed repeater clock command: stable_id=%s "
                    "pubkey_prefix=%s command=%s",
                    stable_id,
                    target.pubkey_prefix,
                    command,
                )
                service_response = await self.hass.services.async_call(
                    MESHCORE_DOMAIN,
                    "execute_command",
                    {"command": command},
                    blocking=True,
                    return_response=True,
                )
            except (HomeAssistantError, ServiceNotFound) as err:
                return self._finish_failure(pending, str(err))
            except Exception as err:  # noqa: BLE001 - service boundary
                return self._finish_failure(pending, f"service call failed: {err}")

            result.service_response = service_response
            if future.done():
                return future.result()
            if not isinstance(service_response, dict):
                return self._finish_failure(
                    pending, "MeshCore send confirmation unavailable"
                )
            if service_response.get("error"):
                return self._finish_failure(
                    pending, f"MeshCore send failed: {service_response['error']}"
                )
            result.state = ClockCheckState.SENT
            self._notify(stable_id)

            try:
                async with asyncio.timeout(self.timeout_seconds):
                    return await future
            except TimeoutError:
                completed_at = self._utc_now()
                result.state = ClockCheckState.TIMED_OUT
                result.error = "clock response timed out"
                result.last_clock_attempt_outcome = ClockAttemptOutcome.TIMEOUT
                result.last_clock_attempt_error = result.error
                self.last_timeout = {
                    "stable_id": stable_id,
                    "pubkey_prefix": target.pubkey_prefix,
                    "requested_at": requested_at,
                    "timed_out_at": completed_at,
                }
                self._append_history(result, requested_at, completed_at)
                self._notify(stable_id)
                return result
        finally:
            self._pending.pop(prefix, None)

    async def async_sync_repeater_clock(
        self,
        repeater_id: str,
        *,
        fleet_sync_run_id: str | None = None,
    ) -> ClockSyncResult:
        """Synchronize one managed repeater and verify it with read-only checks."""
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
        if (
            self._fleet_sync_run_id is not None
            and fleet_sync_run_id != self._fleet_sync_run_id
        ):
            return ClockSyncResult(
                stable_id=target.stable_id,
                pubkey_prefix=target.pubkey_prefix,
                result=ClockSyncState.FAILED,
                started_at=started_at,
                completed_at=self._utc_now(),
                duration_seconds=0.0,
                error="a fleet clock synchronization is already active",
            )
        if self._fleet_run_id is not None:
            return ClockSyncResult(
                stable_id=target.stable_id,
                pubkey_prefix=target.pubkey_prefix,
                result=ClockSyncState.FAILED,
                started_at=started_at,
                completed_at=self._utc_now(),
                duration_seconds=0.0,
                error="a fleet clock check is already active",
            )
        if prefix in self._pending_sync or prefix in self._pending:
            return ClockSyncResult(
                stable_id=target.stable_id,
                pubkey_prefix=target.pubkey_prefix,
                result=ClockSyncState.FAILED,
                started_at=started_at,
                completed_at=self._utc_now(),
                duration_seconds=0.0,
                error="another clock operation is already running for this repeater",
            )

        task = asyncio.current_task()
        if task is not None:
            self._sync_tasks.add(task)
        result_state = self._results[target.stable_id]
        result_state.sync_running = True
        result_state.last_sync_error = None
        result_state.last_sync_response = None
        self._notify(target.stable_id)
        response = ClockSyncResult(
            stable_id=target.stable_id,
            pubkey_prefix=target.pubkey_prefix,
            result=ClockSyncState.FAILED,
            started_at=started_at,
        )

        try:
            try:
                pre_check = await self.async_check_clock(
                    target.stable_id,
                    sync_operation=True,
                    bypass_cooldown=True,
                )
            except ClockManagerError as err:
                return self._finish_sync(
                    response, ClockSyncState.COMMAND_FAILED, str(err)
                )
            if pre_check.state is not ClockCheckState.COMPLETED:
                return self._finish_sync(
                    response,
                    ClockSyncState.COMMAND_FAILED,
                    f"pre-sync clock check failed: {pre_check.error or pre_check.state}",
                )
            response.pre_sync_offset_seconds = pre_check.clock_offset_seconds
            result_state.offset_before_sync_seconds = pre_check.clock_offset_seconds

            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            pending = _PendingClockSync(
                target=target,
                started_at=self._utc_now(),
                future=future,
            )
            self._pending_sync[prefix] = pending
            command = f'send_cmd {target.pubkey_prefix} "clock sync"'
            _LOGGER.debug(
                "Dispatching managed repeater clock sync: stable_id=%s "
                "pubkey_prefix=%s command=%s",
                target.stable_id,
                target.pubkey_prefix,
                command,
            )
            if not self.hass.services.has_service(MESHCORE_DOMAIN, "execute_command"):
                return self._finish_sync(
                    response,
                    ClockSyncState.COMMAND_FAILED,
                    "meshcore.execute_command unavailable",
                )
            try:
                service_response = await self.hass.services.async_call(
                    MESHCORE_DOMAIN,
                    "execute_command",
                    {"command": command},
                    blocking=True,
                    return_response=True,
                )
            except (HomeAssistantError, ServiceNotFound) as err:
                return self._finish_sync(
                    response, ClockSyncState.COMMAND_FAILED, str(err)
                )
            except Exception as err:  # noqa: BLE001 - service boundary
                return self._finish_sync(
                    response,
                    ClockSyncState.COMMAND_FAILED,
                    f"service call failed: {err}",
                )
            if not isinstance(service_response, dict) or service_response.get("error"):
                return self._finish_sync(
                    response,
                    ClockSyncState.COMMAND_FAILED,
                    "MeshCore clock-sync transmission was not accepted",
                )

            try:
                async with asyncio.timeout(self.timeout_seconds):
                    remote_text = await future
            except TimeoutError:
                return self._finish_sync(
                    response,
                    ClockSyncState.TIMEOUT,
                    "clock sync response timed out",
                )

            response.remote_response_text = remote_text
            result_state.last_sync_response = remote_text
            if remote_text == "ERR: clock cannot go backwards":
                return self._finish_sync(
                    response,
                    ClockSyncState.ALREADY_AHEAD,
                    "repeater clock cannot move backwards",
                )
            lowered = remote_text.casefold()
            if (
                "unauthorized" in lowered
                or "permission" in lowered
                or "auth" in lowered
            ):
                return self._finish_sync(
                    response,
                    ClockSyncState.UNAUTHORIZED,
                    remote_text,
                )

            try:
                post_check = await self.async_check_clock(
                    target.stable_id,
                    sync_operation=True,
                    bypass_cooldown=True,
                )
            except ClockManagerError as err:
                return self._finish_sync(
                    response, ClockSyncState.VERIFICATION_FAILED, str(err)
                )
            if post_check.state is not ClockCheckState.COMPLETED:
                return self._finish_sync(
                    response,
                    ClockSyncState.VERIFICATION_FAILED,
                    f"post-sync clock check failed: {post_check.error or post_check.state}",
                )
            response.post_sync_offset_seconds = post_check.clock_offset_seconds
            result_state.offset_after_sync_seconds = post_check.clock_offset_seconds
            return self._finish_sync(response, ClockSyncState.SUCCESS)
        except asyncio.CancelledError:
            return self._finish_sync(
                response, ClockSyncState.CANCELLED, "clock sync cancelled"
            )
        except Exception as err:  # noqa: BLE001 - bounded operation boundary
            return self._finish_sync(response, ClockSyncState.FAILED, str(err))
        finally:
            self._pending_sync.pop(prefix, None)
            result_state.sync_running = False
            self._notify(target.stable_id)
            if task is not None:
                self._sync_tasks.discard(task)

    def _finish_sync(
        self,
        response: ClockSyncResult,
        result: ClockSyncState,
        error: str | None = None,
    ) -> ClockSyncResult:
        """Complete and publish one synchronization result."""
        completed_at = self._utc_now()
        response.result = result
        response.completed_at = completed_at
        response.duration_seconds = max(
            0.0, round((completed_at - response.started_at).total_seconds(), 3)
        )
        response.error = error
        state = self._results.get(response.stable_id)
        if state is not None:
            state.last_sync_result = result
            state.last_sync_time = completed_at
            state.sync_duration_seconds = response.duration_seconds
            state.last_sync_response = response.remote_response_text
            state.last_sync_error = error
            state.offset_before_sync_seconds = response.pre_sync_offset_seconds
            state.offset_after_sync_seconds = response.post_sync_offset_seconds
            self._notify(response.stable_id)
        return response

    @callback
    def _async_handle_raw_event(self, event: Event) -> None:
        """Process only public CONTACT_MSG_RECV events."""
        data = event.data
        if data.get("event_type") != _CONTACT_MESSAGE_EVENT:
            return
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return
        pubkey_prefix = str(payload.get("pubkey_prefix", "")).lower()
        pending_sync = self._pending_sync.get(pubkey_prefix)
        if pending_sync is not None and not pending_sync.future.done():
            event_timestamp = data.get("timestamp")
            text = payload.get("text")
            if (
                isinstance(event_timestamp, (int, float))
                and not isinstance(event_timestamp, bool)
                and event_timestamp >= pending_sync.started_at.timestamp()
                and isinstance(text, str)
                and (
                    text == "OK - clock set"
                    or text.startswith("OK - clock set:")
                    or text == "ERR: clock cannot go backwards"
                    or "unauthorized" in text.casefold()
                    or "permission" in text.casefold()
                    or "auth" in text.casefold()
                )
            ):
                pending_sync.future.set_result(text)
            return
        pending = self._pending.get(pubkey_prefix)
        if pending is None or pending.future.done():
            return

        received_at = self._utc_now()
        text = payload.get("text")
        sender_timestamp = payload.get("sender_timestamp")
        self.last_response = {
            "stable_id": pending.target.stable_id,
            "pubkey_prefix": pubkey_prefix,
            "received_at": received_at,
            "text": text,
            "sender_timestamp": sender_timestamp,
            "SNR": payload.get("SNR"),
        }
        if not isinstance(text, str):
            self._complete_parse_failure(pending, received_at, "missing clock text")
            return
        try:
            parsed = parse_clock_text(text)
        except (TypeError, ValueError) as err:
            self._complete_parse_failure(pending, received_at, str(err), text=text)
            return
        if not isinstance(sender_timestamp, int) or isinstance(sender_timestamp, bool):
            self._complete_parse_failure(
                pending, received_at, "invalid sender_timestamp", text=text
            )
            return
        if abs(parsed.timestamp() - sender_timestamp) > _MAX_TEXT_TIMESTAMP_DIFFERENCE:
            self._complete_parse_failure(
                pending,
                received_at,
                "clock text and sender_timestamp disagree",
                text=text,
            )
            return

        result = self._results[pending.target.stable_id]
        result.state = ClockCheckState.COMPLETED
        result.last_clock_reply = received_at
        result.response_text = text
        result.sender_timestamp = sender_timestamp
        result.clock_rtt_ms = max(
            0, round((self._monotonic() - pending.started_monotonic) * 1000)
        )
        result.clock_offset_seconds = calculate_clock_offset(
            sender_timestamp, received_at
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
        self.last_parse_result = {
            "stable_id": result.stable_id,
            "success": True,
            "parsed_clock": parsed,
            "clock_offset_seconds": result.clock_offset_seconds,
        }
        self._append_history(
            result, pending.requested_at, received_at, include_reply=True
        )
        self._notify(result.stable_id)
        pending.future.set_result(result)

    def _complete_parse_failure(
        self,
        pending: _PendingClockRequest,
        received_at: datetime,
        error: str,
        *,
        text: str | None = None,
    ) -> None:
        result = self._results[pending.target.stable_id]
        result.state = ClockCheckState.FAILED
        result.error = error
        result.last_clock_attempt_outcome = ClockAttemptOutcome.MALFORMED
        result.last_clock_attempt_error = error
        result.last_clock_reply = received_at
        result.response_text = text
        self.last_parse_result = {
            "stable_id": result.stable_id,
            "success": False,
            "error": error,
            "text": text,
        }
        self._append_history(
            result, pending.requested_at, received_at, include_reply=True
        )
        self._notify(result.stable_id)
        pending.future.set_result(result)

    def _finish_failure(self, pending: _PendingClockRequest, error: str) -> ClockResult:
        completed_at = self._utc_now()
        result = self._results[pending.target.stable_id]
        result.state = ClockCheckState.FAILED
        result.error = error
        result.last_clock_attempt_outcome = ClockAttemptOutcome.FAILED
        result.last_clock_attempt_error = error
        self._append_history(result, pending.requested_at, completed_at)
        self._notify(result.stable_id)
        return result

    def _append_history(
        self,
        result: ClockResult,
        requested_at: datetime,
        completed_at: datetime,
        *,
        include_reply: bool = False,
    ) -> None:
        successful = result.state is ClockCheckState.COMPLETED
        self._history.append(
            ClockHistoryEntry(
                stable_id=result.stable_id,
                pubkey_prefix=result.pubkey_prefix,
                requested_at=requested_at,
                completed_at=completed_at,
                state=result.state,
                response_text=result.response_text if include_reply else None,
                sender_timestamp=(result.sender_timestamp if successful else None),
                clock_offset_seconds=(
                    result.clock_offset_seconds if successful else None
                ),
                clock_status=(
                    result.clock_status if successful else ClockStatus.UNKNOWN
                ),
                clock_rtt_ms=result.clock_rtt_ms if successful else None,
                error=result.error,
            )
        )

    def _utc_now(self) -> datetime:
        now = self._now()
        return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)

    @callback
    def _notify(self, stable_id: str) -> None:
        for listener in tuple(self._listeners.get(stable_id, ())):
            listener()
