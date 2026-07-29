"""Per-device calculation coordinator for MeshCore NOC."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    AGING_MAX_AGE,
    FRESH_MAX_AGE,
    MAX_VALID_VOLTAGE,
    MIN_VALID_VOLTAGE,
    STALE_MAX_AGE,
)
from .management import (
    DEFAULT_REPEATER_SETTINGS,
    RepeaterManagementStore,
    RepeaterSettings,
)
from .models import DiscoveredSourceRepeater, ManagedDeviceData
from .naming import managed_device_name

_LOGGER = logging.getLogger(__name__)


def _freshness(
    age_seconds: int | None,
    available: bool,
    fresh_max_age: int = FRESH_MAX_AGE,
    aging_max_age: int = AGING_MAX_AGE,
    offline_max_age: int = STALE_MAX_AGE,
) -> str:
    """Classify source telemetry using the production dashboard thresholds."""
    if not available or age_seconds is None or age_seconds >= offline_max_age:
        return "Offline"
    if age_seconds >= aging_max_age:
        return "Stale"
    if age_seconds >= fresh_max_age:
        return "Aging"
    return "Fresh"


def calculate_health(
    battery: int | None,
    freshness: str,
    battery_warning: int = 40,
    battery_critical: int = 20,
) -> str:
    """Calculate alpha2 health independently from entity presentation."""
    if battery is None:
        return "Unknown"
    if freshness == "Offline" or battery < battery_critical:
        return "Poor"
    if freshness == "Stale" or battery < battery_warning:
        return "Fair"
    if freshness == "Aging" or battery < 80:
        return "Good"
    return "Excellent"


class MeshCoreNocCoordinator(DataUpdateCoordinator[ManagedDeviceData]):
    """Calculate one managed device snapshot for all of its NOC entities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        source: DiscoveredSourceRepeater,
        management_store: RepeaterManagementStore | None = None,
        *,
        legacy_identity: bool = True,
    ) -> None:
        """Initialize a coordinator for one stable managed device."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"MeshCore NOC {source.stable_id}",
            update_interval=timedelta(minutes=1),
            config_entry=config_entry,
        )
        self.config_entry = config_entry
        self.source = source
        self.management_store = management_store
        self.legacy_identity = legacy_identity
        self.last_attempted_update: datetime | None = None
        self.last_successful_update: datetime | None = None
        self._unsub_source_listener: Callable[[], None] | None = None

    def _settings(self) -> RepeaterSettings:
        """Return current per-repeater settings or production defaults."""
        if self.management_store is None:
            return DEFAULT_REPEATER_SETTINGS
        return self.management_store.settings_for(self.source.stable_id)

    @property
    def source_listener_registered(self) -> bool:
        """Return whether the source-state listener is active."""
        return self._unsub_source_listener is not None

    @property
    def next_freshness_transition(self) -> datetime | None:
        """Return the next threshold crossing for available telemetry."""
        if not self.data.source_available or self.data.last_source_update is None:
            return None
        settings = self._settings()
        threshold = {
            "Fresh": settings.fresh_max_age,
            "Aging": settings.aging_max_age,
            "Stale": settings.offline_max_age,
        }.get(self.data.freshness)
        if threshold is None:
            return None
        return self.data.last_source_update + timedelta(seconds=threshold)

    def async_start_source_listener(self) -> None:
        """Subscribe once to the mapped MeshCore voltage source."""
        source_entity = self.source.entities.voltage
        if source_entity is None or self._unsub_source_listener is not None:
            return
        self._unsub_source_listener = async_track_state_change_event(
            self.hass,
            [source_entity],
            self._async_source_state_changed,
        )

    @callback
    def _async_source_state_changed(self, event: Event) -> None:
        """Request one debounced refresh after a source state change."""
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_stop_source_listener(self) -> None:
        """Remove the source listener if it is registered."""
        if self._unsub_source_listener is None:
            return
        self._unsub_source_listener()
        self._unsub_source_listener = None

    async def _async_update_data(self) -> ManagedDeviceData:
        """Read the Alpha1 mapping and calculate all exposed values once."""
        self.last_attempted_update = dt_util.utcnow()
        settings = self._settings()
        source_entity = self.source.entities.voltage
        state = self.hass.states.get(source_entity) if source_entity else None
        source_available = bool(
            state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        )
        raw_voltage: float | None = None
        if source_available and state is not None:
            try:
                raw_voltage = float(state.state)
            except (TypeError, ValueError):
                source_available = False

        calibrated_voltage: float | None = None
        battery_percentage: int | None = None
        if raw_voltage is not None:
            calibrated = raw_voltage + settings.voltage_offset
            if MIN_VALID_VOLTAGE <= calibrated <= MAX_VALID_VOLTAGE:
                calibrated_voltage = round(calibrated, 3)
                percentage = (
                    (calibrated_voltage - settings.empty_voltage)
                    / (settings.full_voltage - settings.empty_voltage)
                    * 100
                )
                battery_percentage = round(max(0, min(100, percentage)))

        last_source_update = state.last_updated if state else None
        age_seconds: int | None = None
        if last_source_update is not None:
            now = dt_util.utcnow()
            updated = last_source_update
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            age_seconds = max(0, int((now - updated).total_seconds()))

        freshness = _freshness(
            age_seconds,
            source_available,
            settings.fresh_max_age,
            settings.aging_max_age,
            settings.offline_max_age,
        )
        data = ManagedDeviceData(
            stable_id=self.source.stable_id,
            managed_device=managed_device_name(
                settings.display_name or self.source.display_name,
                self.source.stable_id,
            ),
            source_entity=source_entity,
            raw_voltage=raw_voltage,
            calibrated_voltage=calibrated_voltage,
            battery_percentage=battery_percentage,
            calibration_offset=settings.voltage_offset,
            empty_voltage=settings.empty_voltage,
            full_voltage=settings.full_voltage,
            last_source_update=last_source_update,
            age_seconds=age_seconds,
            freshness=freshness,
            health=calculate_health(
                battery_percentage,
                freshness,
                settings.battery_warning,
                settings.battery_critical,
            ),
            source_available=source_available,
        )
        self.last_successful_update = dt_util.utcnow()
        return data
