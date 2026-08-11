"""MeshCore NOC integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service as service_helper

from .clock import (
    ClockTarget,
    ManagedRepeaterAddressability,
    MeshCoreNocClockManager,
    NonAddressableRepeater,
)
from .const import (
    ALPHA2_DEVICE_SLUG,
    CONF_AUTO_FLEET_CLOCK_CHECKS,
    CONF_AUTO_FLEET_CLOCK_SYNC,
    CONF_CLOCK_CHECK_COOLDOWN,
    CONF_FLEET_CLOCK_INTERVAL_HOURS,
    CONF_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
    CONF_FLEET_FAILURE_DELAY,
    CONF_FLEET_ROTATING_START,
    CONF_FLEET_SUCCESS_DELAY,
    CONF_MANAGED_REPEATER_IDS,
    CONF_UPDATE_CHANNEL,
    DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    DEFAULT_AUTO_FLEET_CLOCK_SYNC,
    DEFAULT_CLOCK_CHECK_COOLDOWN,
    DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    DEFAULT_FLEET_CLOCK_SYNC_DELAY,
    DEFAULT_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
    DEFAULT_FLEET_FAILURE_DELAY,
    DEFAULT_FLEET_ROTATING_START,
    DEFAULT_FLEET_SUCCESS_DELAY,
    DEFAULT_UPDATE_CHANNEL,
    DOMAIN,
    INTEGRATION_NAME,
    MESHCORE_DOMAIN,
    PLATFORMS,
    SERVICE_CANCEL_CLOCK_CHECK,
    SERVICE_CHECK_ALL_CLOCKS,
    SERVICE_CHECK_CLOCK,
    SERVICE_SYNC_ALL_REPEATER_CLOCKS,
    SERVICE_SYNC_REPEATER_CLOCK,
)
from .coordinator import MeshCoreNocCoordinator
from .dashboard import DashboardSetupResult, async_setup_dashboard
from .discovery import async_discover_repeaters
from .fleet_clock import FleetClockConfig, FleetClockOrchestrator, FleetClockTrigger
from .fleet_sync import (
    FleetClockSyncConfig,
    FleetClockSyncOrchestrator,
    FleetClockSyncTrigger,
)
from .management import (
    RepeaterManagementStore,
    async_register_management_websockets,
)
from .models import DeviceType, DiscoveryResult
from .updater import MeshCoreNocUpdateCoordinator

_RECONCILIATION_DATA = "reconciliation"
_LOGGER = logging.getLogger(__name__)

_MANAGED_ENTITY_SUFFIXES = (
    "calibrated_voltage",
    "calibrated_battery_percentage",
    "health",
    "fresh",
    "clock_offset",
    "clock_status",
)


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """Describe the latest managed-selection reconciliation."""

    created: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegistryCleanupResult:
    """Describe registry records removed during reconciliation."""

    matched_entity_ids: tuple[str, ...] = ()
    removed_entity_count: int = 0
    removed_device_count: int = 0


@dataclass(frozen=True, slots=True)
class ClockTargetDiscovery:
    """Addressable targets and exclusions for the current managed selection."""

    targets: dict[str, ClockTarget]
    non_addressable: tuple[NonAddressableRepeater, ...]
    addressability: tuple[ManagedRepeaterAddressability, ...]


@dataclass(slots=True)
class MeshCoreNocRuntimeData:
    """Runtime state for the config entry."""

    discovery: DiscoveryResult
    coordinators: tuple[MeshCoreNocCoordinator, ...]
    reconciliation: ReconciliationSummary
    update_coordinator: MeshCoreNocUpdateCoordinator
    dashboard: DashboardSetupResult
    clock_manager: MeshCoreNocClockManager
    fleet_clock_orchestrator: FleetClockOrchestrator
    fleet_clock_sync_orchestrator: FleetClockSyncOrchestrator
    management_store: RepeaterManagementStore

    @property
    def coordinator(self) -> MeshCoreNocCoordinator | None:
        """Keep the alpha1 runtime attribute available during migration."""
        return self.coordinators[0] if self.coordinators else None


type MeshCoreNocConfigEntry = ConfigEntry[MeshCoreNocRuntimeData]


async def async_setup(hass: HomeAssistant, _config: dict[str, object]) -> bool:
    """Register the integration-wide administrator management API."""
    async_register_management_websockets(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MeshCoreNocConfigEntry) -> bool:
    """Set up every selected managed MeshCore device."""
    if not hass.config_entries.async_entries(MESHCORE_DOMAIN):
        raise ConfigEntryNotReady("The MeshCore integration is not configured")

    discovery = await async_discover_repeaters(hass)
    selected = tuple(dict.fromkeys(entry.options.get(CONF_MANAGED_REPEATER_IDS, [])))
    management_store = RepeaterManagementStore(
        hass, f"{DOMAIN}.repeater_management.{entry.entry_id}"
    )
    await management_store.async_initialize()
    coordinators: list[MeshCoreNocCoordinator] = []
    legacy_stable_id = _legacy_managed_stable_id(hass, selected)
    try:
        for stable_id in selected:
            source = discovery.repeaters.get(stable_id)
            if source is None:
                continue
            coordinator = MeshCoreNocCoordinator(
                hass,
                entry,
                source,
                management_store,
                legacy_identity=stable_id == legacy_stable_id,
            )
            coordinator.async_start_source_listener()
            await coordinator.async_config_entry_first_refresh()
            coordinators.append(coordinator)
    except ConfigEntryNotReady:
        coordinator.async_stop_source_listener()
        for started_coordinator in coordinators:
            started_coordinator.async_stop_source_listener()
        raise

    if coordinators:
        registry = dr.async_get(hass)
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "noc")},
            name=INTEGRATION_NAME,
            manufacturer="MeshCore NOC",
            model="Network Operations Centre",
        )

    domain_data = hass.data.setdefault(DOMAIN, {})
    reconciliation = domain_data.setdefault(_RECONCILIATION_DATA, {}).pop(
        entry.entry_id,
        ReconciliationSummary(
            created=tuple(coordinator.source.stable_id for coordinator in coordinators)
        ),
    )
    update_coordinator = MeshCoreNocUpdateCoordinator(
        hass, entry.options.get(CONF_UPDATE_CHANNEL, DEFAULT_UPDATE_CHANNEL)
    )
    dashboard = await async_setup_dashboard(hass)
    clock_target_discovery = _clock_targets(coordinators, selected)
    clock_manager = MeshCoreNocClockManager(
        hass,
        clock_target_discovery.targets,
        managed_repeaters={
            stable_id: (
                discovery.repeaters[stable_id].display_name
                if stable_id in discovery.repeaters
                else stable_id
            )
            for stable_id in selected
        },
        non_addressable_repeaters=clock_target_discovery.non_addressable,
        managed_repeater_addressability=clock_target_discovery.addressability,
        cooldown_seconds=int(
            entry.options.get(CONF_CLOCK_CHECK_COOLDOWN, DEFAULT_CLOCK_CHECK_COOLDOWN)
        ),
        clock_thresholds=lambda stable_id: (
            management_store.settings_for(stable_id).clock_warning,
            management_store.settings_for(stable_id).clock_critical,
        ),
    )
    fleet_clock_orchestrator = FleetClockOrchestrator(
        hass,
        clock_manager,
        FleetClockConfig(
            automatic_enabled=bool(
                entry.options.get(
                    CONF_AUTO_FLEET_CLOCK_CHECKS,
                    DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
                )
            ),
            interval_hours=int(
                entry.options.get(
                    CONF_FLEET_CLOCK_INTERVAL_HOURS,
                    DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
                )
            ),
            success_delay_seconds=int(
                entry.options.get(CONF_FLEET_SUCCESS_DELAY, DEFAULT_FLEET_SUCCESS_DELAY)
            ),
            failure_delay_seconds=int(
                entry.options.get(CONF_FLEET_FAILURE_DELAY, DEFAULT_FLEET_FAILURE_DELAY)
            ),
            rotating_start=bool(
                entry.options.get(
                    CONF_FLEET_ROTATING_START, DEFAULT_FLEET_ROTATING_START
                )
            ),
        ),
    )
    fleet_clock_sync_orchestrator = FleetClockSyncOrchestrator(
        hass,
        clock_manager,
        FleetClockSyncConfig(
            automatic_enabled=bool(
                entry.options.get(
                    CONF_AUTO_FLEET_CLOCK_SYNC,
                    DEFAULT_AUTO_FLEET_CLOCK_SYNC,
                )
            ),
            interval_hours=int(
                entry.options.get(
                    CONF_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
                    DEFAULT_FLEET_CLOCK_SYNC_INTERVAL_HOURS,
                )
            ),
            inter_repeater_delay_seconds=DEFAULT_FLEET_CLOCK_SYNC_DELAY,
        ),
        storage_key=f"{DOMAIN}.fleet_clock_sync.{entry.entry_id}",
    )
    await fleet_clock_sync_orchestrator.async_initialize()
    entry.runtime_data = MeshCoreNocRuntimeData(
        discovery,
        tuple(coordinators),
        reconciliation,
        update_coordinator,
        dashboard,
        clock_manager,
        fleet_clock_orchestrator,
        fleet_clock_sync_orchestrator,
        management_store,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    clock_manager.async_start()
    fleet_clock_orchestrator.async_start_scheduler()
    fleet_clock_sync_orchestrator.async_start_scheduler()
    _async_register_clock_services(
        hass,
        clock_manager,
        fleet_clock_orchestrator,
        fleet_clock_sync_orchestrator,
    )
    entry.async_on_unload(clock_manager.async_stop)
    entry.async_on_unload(fleet_clock_orchestrator.async_stop)
    entry.async_on_unload(fleet_clock_sync_orchestrator.async_stop)
    for service_name in (
        SERVICE_CHECK_CLOCK,
        SERVICE_SYNC_REPEATER_CLOCK,
        SERVICE_SYNC_ALL_REPEATER_CLOCKS,
        SERVICE_CHECK_ALL_CLOCKS,
        SERVICE_CANCEL_CLOCK_CHECK,
    ):
        entry.async_on_unload(
            lambda service_name=service_name: hass.services.async_remove(
                DOMAIN, service_name
            )
        )
    hass.async_create_task(
        update_coordinator.async_refresh(),
        "MeshCore NOC initial update check",
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _clock_targets(
    coordinators: list[MeshCoreNocCoordinator],
    selected: tuple[str, ...] = (),
) -> ClockTargetDiscovery:
    """Build public service targets from MeshCore-owned registry identifiers."""
    candidates: dict[str, ClockTarget] = {}
    non_addressable: list[NonAddressableRepeater] = []
    addressability: list[ManagedRepeaterAddressability] = []
    active_ids = {coordinator.source.stable_id for coordinator in coordinators}
    for stable_id in selected:
        if stable_id not in active_ids:
            non_addressable.append(
                NonAddressableRepeater(
                    stable_id=stable_id,
                    friendly_name=stable_id,
                    resolution_sources_checked=(),
                    rejection_reason=(
                        "managed stable_id is not present in active MeshCore discovery"
                    ),
                )
            )
            addressability.append(
                ManagedRepeaterAddressability(
                    stable_id=stable_id,
                    friendly_name=stable_id,
                    device_type="unresolved",
                    resolution_source=None,
                    pubkey_prefix=None,
                    resolution_sources_checked=(),
                    accepted=False,
                    reason=(
                        "rejected: managed stable_id is not present in active "
                        "MeshCore discovery"
                    ),
                )
            )

    for coordinator in coordinators:
        source = coordinator.source
        if source.device_type is DeviceType.CLIENT:
            reason = (
                "rejected: MeshCore metadata explicitly classifies device as client"
            )
            non_addressable.append(
                NonAddressableRepeater(
                    stable_id=source.stable_id,
                    friendly_name=source.display_name,
                    resolution_sources_checked=(
                        source.command_address.resolution_sources_checked
                    ),
                    rejection_reason=reason,
                )
            )
            addressability.append(
                ManagedRepeaterAddressability(
                    stable_id=source.stable_id,
                    friendly_name=source.display_name,
                    device_type=source.device_type,
                    resolution_source=source.command_address.resolution_source,
                    pubkey_prefix=source.pubkey_prefix,
                    resolution_sources_checked=(
                        source.command_address.resolution_sources_checked
                    ),
                    accepted=False,
                    reason=reason,
                )
            )
            continue
        if source.pubkey_prefix is None:
            reason = (
                source.command_address.rejection_reason
                or "no valid 12-character pubkey prefix found"
            )
            non_addressable.append(
                NonAddressableRepeater(
                    stable_id=source.stable_id,
                    friendly_name=source.display_name,
                    resolution_sources_checked=(
                        source.command_address.resolution_sources_checked
                    ),
                    rejection_reason=reason,
                )
            )
            addressability.append(
                ManagedRepeaterAddressability(
                    stable_id=source.stable_id,
                    friendly_name=source.display_name,
                    device_type=source.device_type,
                    resolution_source=source.command_address.resolution_source,
                    pubkey_prefix=None,
                    resolution_sources_checked=(
                        source.command_address.resolution_sources_checked
                    ),
                    accepted=False,
                    reason=f"rejected: {reason}",
                )
            )
            continue
        candidates[source.stable_id] = ClockTarget(
            stable_id=source.stable_id,
            pubkey_prefix=source.pubkey_prefix,
            meshcore_config_entry_id=source.meshcore_config_entry_id,
            label=source.display_name,
        )

    prefix_counts: dict[str, int] = {}
    for target in candidates.values():
        prefix_counts[target.pubkey_prefix] = (
            prefix_counts.get(target.pubkey_prefix, 0) + 1
        )
    targets: dict[str, ClockTarget] = {}
    for stable_id, target in candidates.items():
        if prefix_counts[target.pubkey_prefix] == 1:
            targets[stable_id] = target
            source = next(
                coordinator.source
                for coordinator in coordinators
                if coordinator.source.stable_id == stable_id
            )
            addressability.append(
                ManagedRepeaterAddressability(
                    stable_id=stable_id,
                    friendly_name=target.label,
                    device_type=source.device_type,
                    resolution_source=source.command_address.resolution_source,
                    pubkey_prefix=target.pubkey_prefix,
                    resolution_sources_checked=(
                        source.command_address.resolution_sources_checked
                    ),
                    accepted=True,
                    reason=(
                        "accepted: managed device has one unique valid "
                        "12-character pubkey_prefix"
                    ),
                )
            )
            continue
        source = next(
            coordinator.source
            for coordinator in coordinators
            if coordinator.source.stable_id == stable_id
        )
        non_addressable.append(
            NonAddressableRepeater(
                stable_id=stable_id,
                friendly_name=target.label,
                resolution_sources_checked=(
                    source.command_address.resolution_sources_checked
                ),
                rejection_reason=("pubkey_prefix maps to multiple managed repeaters"),
            )
        )
        addressability.append(
            ManagedRepeaterAddressability(
                stable_id=stable_id,
                friendly_name=target.label,
                device_type=source.device_type,
                resolution_source=source.command_address.resolution_source,
                pubkey_prefix=target.pubkey_prefix,
                resolution_sources_checked=(
                    source.command_address.resolution_sources_checked
                ),
                accepted=False,
                reason=("rejected: pubkey_prefix maps to multiple managed repeaters"),
            )
        )

    return ClockTargetDiscovery(
        targets,
        tuple(non_addressable),
        tuple(sorted(addressability, key=lambda item: item.stable_id)),
    )


@callback
def _async_register_clock_services(
    hass: HomeAssistant,
    manager: MeshCoreNocClockManager,
    fleet: FleetClockOrchestrator,
    fleet_sync: FleetClockSyncOrchestrator,
) -> None:
    """Register single-target and fleet clock services."""

    async def async_check_clock(call: ServiceCall) -> dict[str, object]:
        result = await manager.async_check_clock(call.data["stable_id"])
        return result.as_dict()

    async def async_sync_repeater_clock(call: ServiceCall) -> dict[str, object]:
        result = await manager.async_sync_repeater_clock(call.data["repeater_id"])
        return result.as_dict()

    async def async_check_all_clocks(_call: ServiceCall) -> dict[str, object]:
        return fleet.async_start_run(FleetClockTrigger.MANUAL)

    async def async_sync_all_repeater_clocks(
        _call: ServiceCall,
    ) -> dict[str, object]:
        return await fleet_sync.async_sync_all(FleetClockSyncTrigger.MANUAL)

    async def async_cancel_clock_check(_call: ServiceCall) -> dict[str, object]:
        return fleet.async_cancel_run()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_CLOCK,
        async_check_clock,
        schema=vol.Schema({vol.Required("stable_id"): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_REPEATER_CLOCK,
        async_sync_repeater_clock,
        schema=vol.Schema({vol.Required("repeater_id"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_ALL_CLOCKS,
        async_check_all_clocks,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_ALL_REPEATER_CLOCKS,
        async_sync_all_repeater_clocks,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_CLOCK_CHECK,
        async_cancel_clock_check,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.ONLY,
    )
    service_helper.async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_CHECK_CLOCK,
        {
            "name": "Check repeater clock",
            "description": (
                "Run one manual read-only clock check for a managed, "
                "addressable MeshCore repeater."
            ),
            "fields": {
                "stable_id": {
                    "name": "Managed repeater",
                    "description": (
                        "NOC stable identifier. Friendly names are display-only."
                    ),
                    "required": True,
                    "selector": {
                        "select": {
                            "options": [
                                {
                                    "value": target.stable_id,
                                    "label": target.label,
                                }
                                for target in sorted(
                                    manager.targets.values(),
                                    key=lambda item: item.label.casefold(),
                                )
                            ]
                        }
                    },
                }
            },
        },
    )
    service_helper.async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_CHECK_ALL_CLOCKS,
        {
            "name": "Check all clocks",
            "description": (
                "Start one serialized clock check for every managed, "
                "addressable repeater."
            ),
            "fields": {},
        },
    )
    service_helper.async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_SYNC_ALL_REPEATER_CLOCKS,
        {
            "name": "Synchronize all repeater clocks",
            "description": (
                "Sequentially synchronize every currently managed, active, "
                "addressable repeater to the connected MeshCore companion clock."
            ),
            "fields": {},
        },
    )
    service_helper.async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_SYNC_REPEATER_CLOCK,
        {
            "name": "Synchronize repeater clock",
            "description": (
                "Synchronize one managed repeater to the connected MeshCore "
                "companion clock, then verify the result."
            ),
            "fields": {
                "repeater_id": {
                    "name": "Managed repeater",
                    "description": (
                        "NOC stable identifier. Friendly names are display-only."
                    ),
                    "required": True,
                    "selector": {
                        "select": {
                            "options": [
                                {
                                    "value": target.stable_id,
                                    "label": target.label,
                                }
                                for target in sorted(
                                    manager.targets.values(),
                                    key=lambda item: item.label.casefold(),
                                )
                            ]
                        }
                    },
                }
            },
        },
    )
    service_helper.async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_CANCEL_CLOCK_CHECK,
        {
            "name": "Cancel clock check",
            "description": (
                "Stop the active fleet run before its next repeater dispatch."
            ),
            "fields": {},
        },
    )


def _legacy_managed_stable_id(
    hass: HomeAssistant, selected: list[str] | tuple[str, ...]
) -> str | None:
    """Keep Alpha2 unique IDs attached to their existing managed device."""
    if not selected:
        return None

    entity_registry = er.async_get(hass)
    legacy_entity_id = entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{ALPHA2_DEVICE_SLUG}_calibrated_voltage",
    )
    legacy_entry = (
        entity_registry.async_get(legacy_entity_id) if legacy_entity_id else None
    )
    if legacy_entry is not None and legacy_entry.device_id is not None:
        device = dr.async_get(hass).async_get(legacy_entry.device_id)
        if device is not None:
            for domain, stable_id in device.identifiers:
                if domain == DOMAIN and stable_id in selected:
                    return stable_id

    return selected[0]


async def async_unload_entry(
    hass: HomeAssistant, entry: MeshCoreNocConfigEntry
) -> bool:
    """Unload platforms and remove registry records for deselected repeaters."""
    reconciliation = (
        hass.data.get(DOMAIN, {}).get(_RECONCILIATION_DATA, {}).get(entry.entry_id)
    )
    deselected_ids = set(reconciliation.removed) if reconciliation else set()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for coordinator in entry.runtime_data.coordinators:
            coordinator.async_stop_source_listener()
        cleanup = _remove_deselected_registry_entries(hass, entry, deselected_ids)
        _LOGGER.debug(
            "Managed repeater reconciliation: removed_stable_ids=%s "
            "matched_entity_registry_ids=%s removed_entity_count=%d "
            "removed_device_count=%d",
            sorted(deselected_ids),
            list(cleanup.matched_entity_ids),
            cleanup.removed_entity_count,
            cleanup.removed_device_count,
        )
    return unload_ok


@callback
def _remove_deselected_registry_entries(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    stable_ids: set[str],
) -> RegistryCleanupResult:
    """Remove only NOC-owned registry records for deselected stable IDs."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    matched_entity_ids: set[str] = set()
    target_devices: list[dr.DeviceEntry] = []

    for stable_id in stable_ids:
        device = device_registry.async_get_device(identifiers={(DOMAIN, stable_id)})
        if device is None:
            continue
        target_devices.append(device)
        for entity_entry in er.async_entries_for_device(
            entity_registry,
            device.id,
            include_disabled_entities=True,
        ):
            # The device identifier binds this record to the removed stable ID.
            # Do not require the current config entry ID: registry records from a
            # recreated NOC config entry can legitimately retain the old ID.
            if entity_entry.platform == DOMAIN:
                matched_entity_ids.add(entity_entry.entity_id)

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.platform != DOMAIN:
            continue
        if any(
            _is_managed_unique_id(entity_entry.unique_id, stable_id)
            for stable_id in stable_ids
        ):
            matched_entity_ids.add(entity_entry.entity_id)

    for entity_id in sorted(matched_entity_ids):
        entity_registry.async_remove(entity_id)

    removed_device_count = 0
    for device in target_devices:
        remaining_noc_entries = [
            entity_entry
            for entity_entry in er.async_entries_for_device(
                entity_registry,
                device.id,
                include_disabled_entities=True,
            )
            if entity_entry.platform == DOMAIN
        ]
        all_remaining_entries = er.async_entries_for_device(
            entity_registry,
            device.id,
            include_disabled_entities=True,
        )
        if not remaining_noc_entries and not all_remaining_entries:
            device_registry.async_remove_device(device.id)
            removed_device_count += 1

    return RegistryCleanupResult(
        matched_entity_ids=tuple(sorted(matched_entity_ids)),
        removed_entity_count=len(matched_entity_ids),
        removed_device_count=removed_device_count,
    )


def _is_managed_unique_id(unique_id: str, stable_id: str) -> bool:
    """Recognize canonical Alpha3 managed entity IDs for one stable ID."""
    canonical_prefix = f"managed_repeater_{stable_id}_"
    if unique_id.startswith(canonical_prefix):
        return unique_id.removeprefix(canonical_prefix) in _MANAGED_ENTITY_SUFFIXES

    return False


async def _async_update_listener(
    hass: HomeAssistant, entry: MeshCoreNocConfigEntry
) -> None:
    """Reload the entry and reconcile changes to the managed selection."""
    active_ids = {
        coordinator.source.stable_id for coordinator in entry.runtime_data.coordinators
    }
    selected_ids = set(entry.options.get(CONF_MANAGED_REPEATER_IDS, []))
    hass.data.setdefault(DOMAIN, {}).setdefault(_RECONCILIATION_DATA, {})[
        entry.entry_id
    ] = ReconciliationSummary(
        created=tuple(sorted(selected_ids - active_ids)),
        retained=tuple(sorted(selected_ids & active_ids)),
        removed=tuple(sorted(active_ids - selected_ids)),
    )
    await hass.config_entries.async_reload(entry.entry_id)
