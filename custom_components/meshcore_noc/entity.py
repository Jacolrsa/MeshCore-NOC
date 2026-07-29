"""Shared entity support for MeshCore NOC."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import ALPHA2_DEVICE_SLUG, DOMAIN
from .coordinator import MeshCoreNocCoordinator
from .fleet_clock import FleetClockOrchestrator
from .fleet_sync import FleetClockSyncOrchestrator
from .naming import managed_device_name


def _managed_device_name(coordinator: MeshCoreNocCoordinator) -> str:
    """Return this repeater's normalized discovered name."""
    source = coordinator.source
    return managed_device_name(source.display_name, source.stable_id)


class MeshCoreNocEntity(CoordinatorEntity[MeshCoreNocCoordinator]):
    """Base class for entities backed by one managed-device coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MeshCoreNocCoordinator) -> None:
        """Initialize common identity and device information."""
        super().__init__(coordinator)
        self._managed_device_name = _managed_device_name(coordinator)
        self._identity_slug = (
            ALPHA2_DEVICE_SLUG
            if coordinator.legacy_identity
            else slugify(self._managed_device_name)
        )
        self._unique_id_prefix = (
            ALPHA2_DEVICE_SLUG
            if coordinator.legacy_identity
            else f"managed_repeater_{coordinator.source.stable_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.source.stable_id)},
            name=self._managed_device_name,
            manufacturer="MeshCore",
            model="MeshCore NOC Managed Repeater",
            via_device=(DOMAIN, "noc"),
        )

    def _set_entity_identity(self, domain: str, suffix: str) -> None:
        """Set a stable unique ID and a friendly proposed entity ID."""
        self._attr_unique_id = f"{self._unique_id_prefix}_{suffix}"
        self.entity_id = f"{domain}.meshcore_noc_{self._identity_slug}_{suffix}"


class MeshCoreNocFleetEntity(Entity):
    """Base class for fleet-level NOC entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        orchestrator: FleetClockOrchestrator | FleetClockSyncOrchestrator,
        suffix: str,
    ) -> None:
        """Attach one stable fleet entity to the NOC service device."""
        self.orchestrator = orchestrator
        self._attr_unique_id = f"noc_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "noc")},
            name="MeshCore NOC",
            manufacturer="MeshCore NOC",
            model="Network Operations Centre",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to fleet state changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.orchestrator.async_add_listener(self.async_write_ha_state)
        )
