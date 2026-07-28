"""Binary sensor platform for MeshCore NOC."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MeshCoreNocConfigEntry
from .coordinator import MeshCoreNocCoordinator
from .entity import MeshCoreNocEntity, MeshCoreNocFleetEntity
from .fleet_clock import FleetClockOrchestrator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alpha2 freshness binary sensor."""
    entities: list[BinarySensorEntity] = [
        MeshCoreNocFreshnessBinarySensor(coordinator)
        for coordinator in entry.runtime_data.coordinators
    ]
    entities.append(
        MeshCoreNocClockCheckRunningBinarySensor(
            entry.runtime_data.fleet_clock_orchestrator
        )
    )
    async_add_entities(entities)


class MeshCoreNocFreshnessBinarySensor(MeshCoreNocEntity, BinarySensorEntity):
    """Whether the latest telemetry is in the Fresh band."""

    _attr_translation_key = "freshness"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: MeshCoreNocCoordinator) -> None:
        """Initialize freshness identity for one managed repeater."""
        super().__init__(coordinator)
        self._set_entity_identity("binary_sensor", "fresh")

    @property
    def is_on(self) -> bool:
        """Return whether telemetry is Fresh."""
        return self.coordinator.data.freshness == "Fresh"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return detailed freshness diagnostics."""
        return {
            "freshness_status": self.coordinator.data.freshness,
            "age_seconds": self.coordinator.data.age_seconds,
            "last_source_update": self.coordinator.data.last_source_update,
            "source_available": self.coordinator.data.source_available,
            "managed_device": self.coordinator.data.managed_device,
            "stable_id": self.coordinator.data.stable_id,
        }


class MeshCoreNocClockCheckRunningBinarySensor(
    MeshCoreNocFleetEntity, BinarySensorEntity
):
    """Whether one serialized fleet clock run owns the queue."""

    _attr_translation_key = "clock_check_running"
    _attr_icon = "mdi:clock-fast"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "clock_check_running")
        self.entity_id = "binary_sensor.clock_check_running"

    @property
    def is_on(self) -> bool:
        return self.orchestrator.is_active

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "run": self.orchestrator.current_run,
            "queue": self.orchestrator.queue,
        }
