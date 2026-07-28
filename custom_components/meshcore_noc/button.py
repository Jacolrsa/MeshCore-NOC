"""Clock Intelligence action buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MeshCoreNocConfigEntry
from .clock import MeshCoreNocClockManager
from .coordinator import MeshCoreNocCoordinator
from .entity import MeshCoreNocEntity, MeshCoreNocFleetEntity
from .fleet_clock import FleetClockOrchestrator, FleetClockTrigger


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up fleet clock action buttons."""
    orchestrator = entry.runtime_data.fleet_clock_orchestrator
    entities: list[ButtonEntity] = [
        MeshCoreNocCheckAllClocksButton(orchestrator),
        MeshCoreNocCancelClockCheckButton(orchestrator),
    ]
    for coordinator in entry.runtime_data.coordinators:
        entities.append(
            MeshCoreNocCheckClockButton(coordinator, entry.runtime_data.clock_manager)
        )
    async_add_entities(entities)


class MeshCoreNocCheckClockButton(MeshCoreNocEntity, ButtonEntity):
    """Run the existing single-repeater clock-check path."""

    _attr_translation_key = "check_clock"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        coordinator: MeshCoreNocCoordinator,
        clock_manager: MeshCoreNocClockManager,
    ) -> None:
        super().__init__(coordinator)
        self.clock_manager = clock_manager
        self._set_entity_identity("button", "check_clock")

    async def async_press(self) -> None:
        """Delegate using this managed repeater's stable ID."""
        await self.clock_manager.async_check_clock(self.coordinator.source.stable_id)


class MeshCoreNocCheckAllClocksButton(MeshCoreNocFleetEntity, ButtonEntity):
    """Start one serialized fleet clock run."""

    _attr_translation_key = "check_all_clocks"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "check_all_clocks")
        self.entity_id = "button.check_all_clocks"

    @property
    def available(self) -> bool:
        """Only allow a new fleet run while the queue is idle."""
        return not self.orchestrator.is_active

    async def async_press(self) -> None:
        """Start a manual fleet run."""
        self.orchestrator.async_start_run(FleetClockTrigger.MANUAL)


class MeshCoreNocCancelClockCheckButton(MeshCoreNocFleetEntity, ButtonEntity):
    """Request cooperative cancellation of the active fleet run."""

    _attr_translation_key = "cancel_clock_check"
    _attr_icon = "mdi:cancel"

    def __init__(self, orchestrator: FleetClockOrchestrator) -> None:
        super().__init__(orchestrator, "cancel_clock_check")
        self.entity_id = "button.cancel_clock_check"

    @property
    def available(self) -> bool:
        """Only allow cancellation while a run owns the queue."""
        return self.orchestrator.is_active

    async def async_press(self) -> None:
        """Stop before the next queued dispatch."""
        self.orchestrator.async_cancel_run()
