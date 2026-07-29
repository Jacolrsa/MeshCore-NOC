"""Home Assistant service-contract tests for Clock Intelligence."""

from types import SimpleNamespace

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import service as service_helper

from custom_components.meshcore_noc import (
    _async_register_clock_services,
    _clock_targets,
)
from custom_components.meshcore_noc.clock import ClockTarget, MeshCoreNocClockManager
from custom_components.meshcore_noc.const import DOMAIN
from custom_components.meshcore_noc.discovery import async_discover_repeaters
from custom_components.meshcore_noc.fleet_clock import (
    FleetClockConfig,
    FleetClockOrchestrator,
)
from custom_components.meshcore_noc.models import (
    CommandAddressResolution,
    DeviceType,
    DiscoveredSourceRepeater,
    MissingSourceInformation,
    SourceEntityMappings,
)

from .helpers import add_meshcore_entry, add_repeater


def _register_services(hass, manager):
    fleet = FleetClockOrchestrator(
        hass,
        manager,
        FleetClockConfig(False, 6, 15, 30, False),
    )
    _async_register_clock_services(hass, manager, fleet)
    return fleet


def _source(
    stable_id: str,
    prefix: str | None,
    name: str,
    device_type: DeviceType = DeviceType.REPEATER,
) -> DiscoveredSourceRepeater:
    """Build one resolved discovery record for target-selection tests."""
    resolution = CommandAddressResolution(
        pubkey_prefix=prefix,
        resolution_source="explicit_pubkey_prefix" if prefix else None,
        resolution_sources_checked=("explicit_pubkey_prefix",),
        rejection_reason=None
        if prefix
        else "no valid 12-character pubkey prefix found",
    )
    return DiscoveredSourceRepeater(
        stable_id=stable_id,
        display_name=name,
        device_registry_id=f"device-{stable_id}",
        meshcore_config_entry_id="meshcore-entry",
        entities=SourceEntityMappings(),
        missing=MissingSourceInformation(),
        device_type=device_type,
        pubkey_prefix=prefix,
        command_address=resolution,
    )


async def test_service_selector_values_match_accepted_stable_ids(
    hass: HomeAssistant,
) -> None:
    """The UI submits stable IDs that the backend resolves to exact prefixes."""
    manager = MeshCoreNocClockManager(
        hass,
        {
            "01c1a4fa32c6": ClockTarget(
                "01c1a4fa32c6",
                "01c1a4fa32c6",
                "meshcore-entry",
                "Laguna2",
            )
        },
        managed_repeaters={
            "01c1a4fa32c6": "Laguna2",
            "managed-without-address": "No Address",
        },
        cooldown_seconds=300,
    )
    fleet = _register_services(hass, manager)

    descriptions = await service_helper.async_get_all_descriptions(hass)
    options = descriptions[DOMAIN]["check_clock"]["fields"]["stable_id"]["selector"][
        "select"
    ]["options"]
    sync_options = descriptions[DOMAIN]["sync_repeater_clock"]["fields"]["repeater_id"][
        "selector"
    ]["select"]["options"]

    assert options == [{"value": "01c1a4fa32c6", "label": "Laguna2"}]
    assert sync_options == options
    assert hass.services.has_service(DOMAIN, "sync_repeater_clock")
    target = manager.resolve_target(options[0]["value"])
    assert target.stable_id == "01c1a4fa32c6"
    assert target.pubkey_prefix == "01c1a4fa32c6"
    assert descriptions[DOMAIN]["check_all_clocks"]["fields"] == {}
    assert descriptions[DOMAIN]["cancel_clock_check"]["fields"] == {}
    service = hass.services.async_services()[DOMAIN]["sync_repeater_clock"]
    with pytest.raises(vol.Invalid, match="repeater_id"):
        service.schema({})
    fleet.async_stop()


async def test_selector_includes_every_uniquely_addressable_managed_repeater(
    hass: HomeAssistant,
) -> None:
    """Target discovery includes all stable-ID forms and explains exclusions."""
    sources = (
        _source("01c1a4fa32c6", "01c1a4fa32c6", "Laguna2"),
        _source("entry_repeater_112233445566", "112233445566", "Aurora"),
        _source("legacy-node", "223344556677", "Saldanha"),
        _source(
            "unusual stable id",
            "334455667788",
            "ProMicro Repeater",
            DeviceType.UNKNOWN,
        ),
        _source("managed-client", "556677889900", "Handset", DeviceType.CLIENT),
        _source("missing-prefix", None, "Missing"),
        _source("duplicate-a", "445566778899", "Duplicate A"),
        _source("duplicate-b", "445566778899", "Duplicate B"),
    )
    coordinators = [SimpleNamespace(source=source) for source in sources]
    discovery = _clock_targets(
        coordinators,
        tuple(source.stable_id for source in sources),
    )
    manager = MeshCoreNocClockManager(
        hass,
        discovery.targets,
        managed_repeaters={source.stable_id: source.display_name for source in sources},
        non_addressable_repeaters=discovery.non_addressable,
        cooldown_seconds=300,
    )
    fleet = _register_services(hass, manager)

    descriptions = await service_helper.async_get_all_descriptions(hass)
    options = descriptions[DOMAIN]["check_clock"]["fields"]["stable_id"]["selector"][
        "select"
    ]["options"]

    assert {option["value"] for option in options} == {
        "01c1a4fa32c6",
        "entry_repeater_112233445566",
        "legacy-node",
        "unusual stable id",
    }
    assert {option["label"] for option in options} == {
        "Laguna2",
        "Aurora",
        "Saldanha",
        "ProMicro Repeater",
    }
    rejected = {
        item.stable_id: item.rejection_reason for item in discovery.non_addressable
    }
    assert rejected["missing-prefix"] == ("no valid 12-character pubkey prefix found")
    assert rejected["duplicate-a"] == (
        "pubkey_prefix maps to multiple managed repeaters"
    )
    assert rejected["duplicate-b"] == (
        "pubkey_prefix maps to multiple managed repeaters"
    )
    missing_diagnostics = next(
        item.as_dict()
        for item in discovery.non_addressable
        if item.stable_id == "missing-prefix"
    )
    assert missing_diagnostics == {
        "stable_id": "missing-prefix",
        "friendly_name": "Missing",
        "resolution_sources_checked": ["explicit_pubkey_prefix"],
        "rejection_reason": "no valid 12-character pubkey prefix found",
    }
    addressability = {
        item.stable_id: item.as_dict() for item in discovery.addressability
    }
    assert addressability["unusual stable id"] == {
        "stable_id": "unusual stable id",
        "friendly_name": "ProMicro Repeater",
        "device_type": "unknown",
        "resolution_source": "explicit_pubkey_prefix",
        "pubkey_prefix": "334455667788",
        "resolution_sources_checked": ["explicit_pubkey_prefix"],
        "accepted": True,
        "reason": (
            "accepted: managed device has one unique valid 12-character pubkey_prefix"
        ),
    }
    assert addressability["managed-client"]["accepted"] is False
    assert addressability["managed-client"]["reason"] == (
        "rejected: MeshCore metadata explicitly classifies device as client"
    )
    assert len(addressability) == len(sources)
    fleet.async_stop()


async def test_laguna_style_unknown_type_with_live_prefix_is_addressable(
    hass: HomeAssistant,
) -> None:
    """Optional type metadata cannot hide a managed device with an exact prefix."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="01c1a4fa32c6",
        name="Laguna2",
        model=None,
    )
    source = (await async_discover_repeaters(hass)).repeaters["01c1a4fa32c6"]
    assert source.device_type is DeviceType.UNKNOWN

    discovery = _clock_targets(
        [SimpleNamespace(source=source)],
        ("01c1a4fa32c6",),
    )

    assert discovery.targets["01c1a4fa32c6"].pubkey_prefix == "01c1a4fa32c6"
    assert discovery.addressability[0].accepted is True
    assert discovery.addressability[0].resolution_source == "device_identifier"
