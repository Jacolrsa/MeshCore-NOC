"""Diagnostics for MeshCore NOC."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import MeshCoreNocConfigEntry
from .const import (
    CONF_CLOCK_CHECK_COOLDOWN,
    CONF_UPDATE_CHANNEL,
    DEFAULT_CLOCK_CHECK_COOLDOWN,
    DEFAULT_UPDATE_CHANNEL,
    DOMAIN,
    INTEGRATION_VERSION,
)
from .coordinator import MeshCoreNocCoordinator
from .models import DeviceType
from .updater import version_is_newer


def _confidence_label(score: int) -> str:
    """Return a human-readable confidence band."""
    if score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MeshCoreNocConfigEntry
) -> dict[str, Any]:
    """Return discovery metadata without telemetry history or secrets."""
    result = entry.runtime_data.discovery
    selected = list(entry.options.get("managed_repeater_ids", []))
    active_ids = [
        coordinator.source.stable_id for coordinator in entry.runtime_data.coordinators
    ]
    duplicate_detection = _duplicate_detection(hass, entry, active_ids)
    updater = entry.runtime_data.update_coordinator
    fleet = entry.runtime_data.fleet_clock_orchestrator
    retained_results = {}
    for stable_id in entry.runtime_data.clock_manager.targets:
        clock_result = entry.runtime_data.clock_manager.result_for(stable_id)
        if clock_result is not None:
            retained_results[stable_id] = {
                **clock_result.as_dict(),
                "clock_data_age_seconds": (
                    entry.runtime_data.clock_manager.clock_data_age_seconds(stable_id)
                ),
            }
    devices = []
    type_counts = {device_type: 0 for device_type in DeviceType}
    for repeater in result.repeaters.values():
        type_counts[repeater.device_type] += 1
        mappings = {
            role: {
                "domain": entity_id.split(".", 1)[0],
                "entity_id": entity_id,
            }
            for role, entity_id in repeater.entities.as_dict().items()
            if entity_id is not None
        }
        devices.append(
            {
                "stable_id": repeater.stable_id,
                "display_name": repeater.display_name,
                "device_type": repeater.device_type,
                "device_type_method": repeater.device_type_method,
                "confidence_score": repeater.confidence_score,
                "confidence": _confidence_label(repeater.confidence_score),
                "mapping_method": repeater.mapping_method,
                "source_entity_count": repeater.source_entity_count,
                "meshcore_config_entry_id": repeater.meshcore_config_entry_id,
                "source_entities": mappings,
                "missing_source_roles": list(repeater.missing.roles),
                "warnings": list(repeater.warnings),
                "public_key_available": repeater.public_key is not None,
                "pubkey_prefix": repeater.pubkey_prefix,
                "command_address_resolution_source": (
                    repeater.command_address.resolution_source
                ),
                "resolution_sources_checked": list(
                    repeater.command_address.resolution_sources_checked
                ),
                "command_address_rejection_reason": (
                    repeater.command_address.rejection_reason
                ),
            }
        )

    return {
        "integration_version": INTEGRATION_VERSION,
        "meshcore_config_entries_found": list(result.meshcore_config_entry_ids),
        "discovered_device_count": len(result.repeaters),
        "discovered_repeater_count": type_counts[DeviceType.REPEATER],
        "repeaters_discovered": type_counts[DeviceType.REPEATER],
        "clients_discovered": type_counts[DeviceType.CLIENT],
        "unknown_devices": type_counts[DeviceType.UNKNOWN],
        "managed_repeater_ids": selected,
        "configured_stable_ids": selected,
        "active_stable_ids": active_ids,
        "configured_managed_repeater_count": len(selected),
        "active_managed_repeater_count": len(entry.runtime_data.coordinators),
        "unresolved_managed_repeater_ids": [
            stable_id for stable_id in selected if stable_id not in result.repeaters
        ],
        "managed_devices": [
            _managed_device_diagnostics(hass, coordinator)
            for coordinator in entry.runtime_data.coordinators
        ],
        "managed_device_names": {
            coordinator.source.stable_id: coordinator.data.managed_device
            for coordinator in entry.runtime_data.coordinators
        },
        "clock_intelligence": {
            "managed_repeaters_total": len(selected),
            "addressable_repeaters_total": len(
                entry.runtime_data.clock_manager.targets
            ),
            "non_addressable_repeaters": [
                repeater.as_dict()
                for repeater in (
                    entry.runtime_data.clock_manager.non_addressable_repeaters
                )
            ],
            "managed_repeater_addressability": [
                repeater.as_dict()
                for repeater in (
                    entry.runtime_data.clock_manager.managed_repeater_addressability
                )
            ],
            "cooldown_seconds": entry.options.get(
                CONF_CLOCK_CHECK_COOLDOWN, DEFAULT_CLOCK_CHECK_COOLDOWN
            ),
            "outstanding_requests": entry.runtime_data.clock_manager.outstanding_requests,
            "last_request": entry.runtime_data.clock_manager.last_request,
            "last_response": entry.runtime_data.clock_manager.last_response,
            "last_parse_result": entry.runtime_data.clock_manager.last_parse_result,
            "last_timeout": entry.runtime_data.clock_manager.last_timeout,
            "history": entry.runtime_data.clock_manager.history,
            "retained_results": retained_results,
            "fleet_health": entry.runtime_data.clock_manager.fleet_health,
            "fleet": {
                "configuration": fleet.config.as_dict(),
                "current_run": fleet.current_run,
                "scheduler_state": fleet.scheduler_state,
                "next_scheduled_run": fleet.next_scheduled_run,
                "scheduled_runs_skipped": fleet.scheduled_runs_skipped,
                "last_summary": fleet.last_summary,
                "history": fleet.history,
                "queue": fleet.queue,
                "non_addressable_repeaters": [
                    repeater.as_dict()
                    for repeater in (
                        entry.runtime_data.clock_manager.non_addressable_repeaters
                    )
                ],
            },
        },
        "reconciliation": {
            "created": list(entry.runtime_data.reconciliation.created),
            "retained": list(entry.runtime_data.reconciliation.retained),
            "removed": list(entry.runtime_data.reconciliation.removed),
        },
        "duplicate_detection": duplicate_detection,
        "update": {
            "selected_channel": entry.options.get(
                CONF_UPDATE_CHANNEL, DEFAULT_UPDATE_CHANNEL
            ),
            "installed_version": INTEGRATION_VERSION,
            "latest_known_version": updater.data.latest_version,
            "update_available": (
                version_is_newer(updater.data.latest_version, INTEGRATION_VERSION)
                if updater.data.latest_version is not None
                else None
            ),
            "last_check_time": updater.last_check_time,
            "last_successful_check": updater.last_successful_check,
            "source_url_type": updater.data.source_url_type,
            "branch": updater.data.branch,
            "commit_sha": updater.data.commit_sha,
            "commit_url": updater.data.commit_url,
            "last_error": updater.last_check_error,
            "installation_state": updater.installation_state,
        },
        "repeaters": devices,
        "discovery_warnings": list(result.warnings),
    }


def _duplicate_detection(
    hass: HomeAssistant,
    entry: MeshCoreNocConfigEntry,
    active_ids: list[str],
) -> dict[str, Any]:
    """Report duplicate managed identities without exposing source data."""
    duplicate_coordinator_ids = sorted(
        stable_id for stable_id in set(active_ids) if active_ids.count(stable_id) > 1
    )
    device_registry = dr.async_get(hass)
    duplicate_device_ids = sorted(
        stable_id
        for stable_id in set(active_ids)
        if sum(
            (DOMAIN, stable_id) in device.identifiers
            for device in device_registry.devices.values()
        )
        > 1
    )
    entity_entries = er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    )
    unique_ids = [
        entity_entry.unique_id
        for entity_entry in entity_entries
        if entity_entry.platform == DOMAIN
    ]
    duplicate_entity_unique_ids = sorted(
        unique_id for unique_id in set(unique_ids) if unique_ids.count(unique_id) > 1
    )
    return {
        "duplicates_detected": bool(
            duplicate_coordinator_ids
            or duplicate_device_ids
            or duplicate_entity_unique_ids
        ),
        "coordinator_stable_ids": duplicate_coordinator_ids,
        "device_stable_ids": duplicate_device_ids,
        "entity_unique_ids": duplicate_entity_unique_ids,
    }


def _managed_device_diagnostics(
    hass: HomeAssistant, coordinator: MeshCoreNocCoordinator
) -> dict[str, Any]:
    """Return safe runtime details for one managed-device coordinator."""
    data = coordinator.data
    source_state = (
        hass.states.get(data.source_entity) if data.source_entity is not None else None
    )
    clock_result = coordinator.config_entry.runtime_data.clock_manager.result_for(
        coordinator.source.stable_id
    )
    return {
        "stable_id": data.stable_id,
        "managed_device": data.managed_device,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                str(coordinator.last_exception) if coordinator.last_exception else None
            ),
            "last_successful_update": coordinator.last_successful_update,
            "last_attempted_update": coordinator.last_attempted_update,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "source_listener_registered": coordinator.source_listener_registered,
        },
        "source": {
            "entity_id": data.source_entity,
            "current_state": source_state.state if source_state else None,
            "available": data.source_available,
            "last_changed": source_state.last_changed if source_state else None,
            "last_updated": source_state.last_updated if source_state else None,
        },
        "calculated_values": {
            "raw_voltage": data.raw_voltage,
            "calibrated_voltage": data.calibrated_voltage,
            "battery_percentage": data.battery_percentage,
        },
        "calibration": {
            "offset": data.calibration_offset,
            "empty_voltage": data.empty_voltage,
            "full_voltage": data.full_voltage,
        },
        "freshness": {
            "status": data.freshness,
            "age_seconds": data.age_seconds,
            "last_source_update": data.last_source_update,
            "next_expected_transition": coordinator.next_freshness_transition,
        },
        "health": data.health,
        "clock": (
            {
                **clock_result.as_dict(),
                "clock_data_age_seconds": (
                    coordinator.config_entry.runtime_data.clock_manager.clock_data_age_seconds(
                        coordinator.source.stable_id
                    )
                ),
            }
            if clock_result is not None
            else None
        ),
    }
