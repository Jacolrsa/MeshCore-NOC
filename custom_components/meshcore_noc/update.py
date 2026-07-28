"""Native Home Assistant update entity for MeshCore NOC."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MeshCoreNocConfigEntry
from .const import DOMAIN, INTEGRATION_NAME, INTEGRATION_VERSION
from .updater import MeshCoreNocUpdateCoordinator, version_is_newer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one controller-scoped development update entity."""
    async_add_entities([MeshCoreNocUpdateEntity(entry.runtime_data.update_coordinator)])


class MeshCoreNocUpdateEntity(
    CoordinatorEntity[MeshCoreNocUpdateCoordinator], UpdateEntity
):
    """Install validated MeshCore NOC development-channel updates."""

    _attr_has_entity_name = True
    _attr_translation_key = "update"
    _attr_unique_id = "meshcore_noc_update"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_title = INTEGRATION_NAME
    entity_id = "update.meshcore_noc_update"

    def __init__(self, coordinator: MeshCoreNocUpdateCoordinator) -> None:
        """Attach the updater only to the NOC controller device."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "noc")},
            name=INTEGRATION_NAME,
            manufacturer="MeshCore NOC",
            model="Network Operations Centre",
        )

    @property
    def installed_version(self) -> str:
        """Return the version currently loaded by Home Assistant."""
        return INTEGRATION_VERSION

    @property
    def latest_version(self) -> str | None:
        """Return the latest successfully checked development version."""
        return self.coordinator.data.latest_version

    @property
    def release_summary(self) -> str | None:
        """Return a bounded summary from the matching changelog section."""
        return self.coordinator.data.release_summary

    @property
    def release_url(self) -> str | None:
        """Return the page describing the selected remote build."""
        return self.coordinator.data.release_url

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose safe channel and development metadata."""
        return {
            "update_channel": self.coordinator.channel,
            "branch": self.coordinator.data.branch,
            "commit_sha": self.coordinator.data.commit_sha,
            "commit_url": self.coordinator.data.commit_url,
            "commit_message": self.coordinator.data.commit_message,
            "commit_timestamp": self.coordinator.data.commit_timestamp,
            "last_check_error": self.coordinator.last_check_error,
        }

    @property
    def in_progress(self) -> bool:
        """Return whether an installation currently holds the install lock."""
        return self.coordinator._install_lock.locked()

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Compare development prereleases with AwesomeVersion support."""
        return version_is_newer(latest_version, installed_version)

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: object
    ) -> None:
        """Install the latest checked branch version with an internal backup."""
        if version is not None and version != self.latest_version:
            raise ValueError("Installing an arbitrary version is not supported")
        await self.coordinator.async_install_latest()

    async def async_release_notes(self) -> str | None:
        """Return only the offered version's changelog section."""
        return self.coordinator.data.release_notes

    async def async_update(self) -> None:
        """Allow Home Assistant's entity refresh action to force a check."""
        await self.coordinator.async_request_refresh()
