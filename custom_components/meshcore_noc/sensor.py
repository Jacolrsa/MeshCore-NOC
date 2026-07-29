"""Sensor platform for MeshCore NOC."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MeshCoreNocConfigEntry
from .clock import (
    ClockResult,
    MeshCoreNocClockManager,
    clock_status_label,
)
from .coordinator import MeshCoreNocCoordinator
from .entity import MeshCoreNocEntity, MeshCoreNocFleetEntity
from .fleet_clock import FleetClockOrchestrator, FleetClockState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the three alpha2 sensors."""
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.coordinators:
        entities.extend(
            (
                MeshCoreNocVoltageSensor(coordinator),
                MeshCoreNocBatterySensor(coordinator),
                MeshCoreNocHealthSensor(coordinator),
            )
        )
        if (
            entry.runtime_data.clock_manager.result_for(coordinator.source.stable_id)
            is not None
        ):
            entities.extend(
                (
                    MeshCoreNocClockOffsetSensor(
                        coordinator, entry.runtime_data.clock_manager
                    ),
                    MeshCoreNocClockStatusSensor(
                        coordinator, entry.runtime_data.clock_manager
                    ),
                )
            )
    orchestrator = entry.runtime_data.fleet_clock_orchestrator
    entities.extend(
        (
            MeshCoreNocClockCheckProgressSensor(orchestrator),
            MeshCoreNocClockCheckStateSensor(orchestrator),
            MeshCoreNocLastFleetClockCheckSensor(orchestrator),
            MeshCoreNocFleetClockHealthSensor(
                orchestrator, entry.runtime_data.clock_manager
            ),
        )
    )
    async_add_entities(entities)


class MeshCoreNocVoltageSensor(MeshCoreNocEntity, SensorEntity):
    """Calibrated voltage."""

    _attr_translation_key = "calibrated_voltage"
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: MeshCoreNocCoordinator) -> None:
        """Initialize voltage identity for one managed repeater."""
        super().__init__(coordinator)
        self._set_entity_identity("sensor", "calibrated_voltage")

    @property
    def native_value(self) -> float | None:
        """Return calibrated voltage."""
        return self.coordinator.data.calibrated_voltage

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return voltage diagnostics."""
        data = self.coordinator.data
        return {
            "source_entity": data.source_entity,
            "raw_voltage": data.raw_voltage,
            "calibration_offset": data.calibration_offset,
            "last_source_update": data.last_source_update,
            "managed_device": data.managed_device,
            "stable_id": data.stable_id,
        }


class MeshCoreNocBatterySensor(MeshCoreNocEntity, SensorEntity):
    """Calculated battery percentage."""

    _attr_translation_key = "calibrated_battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MeshCoreNocCoordinator) -> None:
        """Initialize battery identity for one managed repeater."""
        super().__init__(coordinator)
        self._set_entity_identity("sensor", "calibrated_battery_percentage")

    @property
    def native_value(self) -> int | None:
        """Return calculated battery percentage."""
        return self.coordinator.data.battery_percentage

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return battery and calibration diagnostics."""
        data = self.coordinator.data
        return {
            "source_entity": data.source_entity,
            "calibrated_voltage": data.calibrated_voltage,
            "battery_empty_voltage": data.empty_voltage,
            "battery_full_voltage": data.full_voltage,
            "last_source_update": data.last_source_update,
            "managed_device": data.managed_device,
            "stable_id": data.stable_id,
        }


class MeshCoreNocHealthSensor(MeshCoreNocEntity, SensorEntity):
    """First-generation managed-device health."""

    _attr_translation_key = "health"
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: MeshCoreNocCoordinator) -> None:
        """Initialize health identity for one managed repeater."""
        super().__init__(coordinator)
        self._set_entity_identity("sensor", "health")

    @property
    def native_value(self) -> str:
        """Return health classification."""
        return self.coordinator.data.health

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return health inputs and diagnostics."""
        return {
            "battery_percentage": self.coordinator.data.battery_percentage,
            "freshness_status": self.coordinator.data.freshness,
            "age_seconds": self.coordinator.data.age_seconds,
            "managed_device": self.coordinator.data.managed_device,
            "stable_id": self.coordinator.data.stable_id,
        }


class _MeshCoreNocClockSensor(MeshCoreNocEntity, SensorEntity):
    """Shared event-driven clock sensor support."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MeshCoreNocCoordinator,
        clock_manager: MeshCoreNocClockManager,
    ) -> None:
        super().__init__(coordinator)
        self.clock_manager = clock_manager

    async def async_added_to_hass(self) -> None:
        """Subscribe to clock-manager result changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.clock_manager.async_add_listener(
                self.coordinator.source.stable_id,
                self.async_write_ha_state,
            )
        )

    @property
    def clock_result(self) -> ClockResult:
        """Return this sensor's managed clock result."""
        result = self.clock_manager.result_for(self.coordinator.source.stable_id)
        if result is None:
            raise RuntimeError("Clock sensor created without a managed clock target")
        return result

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the bounded latest request diagnostics."""
        result = self.clock_result
        return {
            "last_clock_check": result.last_clock_check,
            "last_clock_reply": result.last_clock_reply,
            "clock_rtt_ms": result.clock_rtt_ms,
            "request_state": result.state,
            "response_text": result.response_text,
            "sender_timestamp": result.sender_timestamp,
            "last_error": result.error,
            "last_successful_clock_check": result.last_successful_clock_check,
            "last_clock_attempt": result.last_clock_attempt,
            "last_clock_attempt_outcome": result.last_clock_attempt_outcome,
            "last_clock_attempt_error": result.last_clock_attempt_error,
            "last_sync_result": result.last_sync_result,
            "last_sync_time": result.last_sync_time,
            "offset_before_sync_seconds": result.offset_before_sync_seconds,
            "offset_after_sync_seconds": result.offset_after_sync_seconds,
            "sync_duration_seconds": result.sync_duration_seconds,
            "last_sync_response": result.last_sync_response,
            "last_sync_error": result.last_sync_error,
            "sync_running": result.sync_running,
            "clock_data_age_seconds": self.clock_manager.clock_data_age_seconds(
                result.stable_id
            ),
            "check_history": [
                entry
                for entry in self.clock_manager.history
                if entry["stable_id"] == result.stable_id
            ],
            "managed_device": self.coordinator.data.managed_device,
            "stable_id": result.stable_id,
            "pubkey_prefix": result.pubkey_prefix,
        }


class MeshCoreNocClockOffsetSensor(_MeshCoreNocClockSensor):
    """Signed repeater clock offset in seconds."""

    _attr_translation_key = "clock_offset"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:clock-fast"

    def __init__(
        self,
        coordinator: MeshCoreNocCoordinator,
        clock_manager: MeshCoreNocClockManager,
    ) -> None:
        super().__init__(coordinator, clock_manager)
        self._set_entity_identity("sensor", "clock_offset")

    @property
    def native_value(self) -> int | None:
        """Return positive-ahead, negative-behind offset."""
        return self.clock_result.clock_offset_seconds


class MeshCoreNocClockStatusSensor(_MeshCoreNocClockSensor):
    """Human-readable repeater clock drift status."""

    _attr_translation_key = "clock_status"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        coordinator: MeshCoreNocCoordinator,
        clock_manager: MeshCoreNocClockManager,
    ) -> None:
        super().__init__(coordinator, clock_manager)
        self._set_entity_identity("sensor", "clock_status")

    @property
    def native_value(self) -> str:
        """Return the required public clock status label."""
        return clock_status_label(self.clock_result.clock_status)


class _MeshCoreNocFleetClockSensor(MeshCoreNocFleetEntity, SensorEntity):
    """Shared fleet diagnostic sensor support."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose current queue state as attributes."""
        return {
            "current_run": self.orchestrator.current_run,
            "queue": self.orchestrator.queue,
            "next_scheduled_run": self.orchestrator.next_scheduled_run,
            "automatic_enabled": self.orchestrator.config.automatic_enabled,
        }


class MeshCoreNocClockCheckProgressSensor(_MeshCoreNocFleetClockSensor):
    """Completed targets over the current snapshot size."""

    _attr_translation_key = "clock_check_progress"
    _attr_icon = "mdi:progress-clock"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "clock_check_progress")
        self.entity_id = "sensor.clock_check_progress"

    @property
    def native_value(self) -> str:
        return self.orchestrator.progress


class MeshCoreNocClockCheckStateSensor(_MeshCoreNocFleetClockSensor):
    """Human-readable fleet lifecycle state."""

    _attr_translation_key = "clock_check_state"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "clock_check_state")
        self.entity_id = "sensor.clock_check_state"

    @property
    def native_value(self) -> str:
        run = self.orchestrator.current_run
        state = run["state"] if run else FleetClockState.IDLE
        return {
            FleetClockState.IDLE: "Idle",
            FleetClockState.QUEUED: "Queued",
            FleetClockState.RUNNING: "Running",
            FleetClockState.WAITING: "Waiting",
            FleetClockState.CANCELLING: "Cancelling",
            FleetClockState.CANCELLED: "Cancelled",
            FleetClockState.COMPLETED: "Completed",
            FleetClockState.COMPLETED_WITH_ERRORS: "Completed with errors",
            FleetClockState.FAILED: "Failed",
        }[FleetClockState(state)]


class MeshCoreNocLastFleetClockCheckSensor(_MeshCoreNocFleetClockSensor):
    """Completion timestamp of the latest fleet run."""

    _attr_translation_key = "last_fleet_clock_check"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "last_fleet_clock_check")
        self.entity_id = "sensor.last_fleet_clock_check"

    @property
    def native_value(self):
        summary = self.orchestrator.last_summary
        return summary["completed_at"] if summary else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            **super().extra_state_attributes,
            "last_summary": self.orchestrator.last_summary,
        }


class MeshCoreNocFleetClockHealthSensor(_MeshCoreNocFleetClockSensor):
    """Fleet clock-health counts derived from retained successful readings."""

    _attr_translation_key = "fleet_clock_health"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        orchestrator: FleetClockOrchestrator,
        clock_manager: MeshCoreNocClockManager,
    ) -> None:
        super().__init__(orchestrator, "fleet_clock_health")
        self.clock_manager = clock_manager
        self.entity_id = "sensor.fleet_clock_health"

    async def async_added_to_hass(self) -> None:
        """Refresh after either fleet or individual clock state changes."""
        await super().async_added_to_hass()
        for stable_id in self.clock_manager.targets:
            self.async_on_remove(
                self.clock_manager.async_add_listener(
                    stable_id, self.async_write_ha_state
                )
            )

    @property
    def native_value(self) -> str:
        """Return the highest fleet clock severity."""
        health = self.clock_manager.fleet_health
        if health["critical"]:
            return "Critical"
        if health["drift"]:
            return "Drift"
        if health["minor_drift"]:
            return "Minor Drift"
        if health["in_sync"]:
            return "In Sync"
        return "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose all category counts and actionable repeater names."""
        return {
            **super().extra_state_attributes,
            **self.clock_manager.fleet_health,
        }
