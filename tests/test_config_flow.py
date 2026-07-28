"""Tests for MeshCore NOC config and options flows."""

from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshcore_noc.config_flow import (
    _device_label,
    _selection_options,
    _ui_display_name,
)
from custom_components.meshcore_noc.const import (
    CONF_AUTO_FLEET_CLOCK_CHECKS,
    CONF_CLOCK_CHECK_COOLDOWN,
    CONF_FLEET_CLOCK_INTERVAL_HOURS,
    CONF_FLEET_FAILURE_DELAY,
    CONF_FLEET_ROTATING_START,
    CONF_FLEET_SUCCESS_DELAY,
    CONF_MANAGED_REPEATER_IDS,
    CONF_UPDATE_CHANNEL,
    DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    DEFAULT_CLOCK_CHECK_COOLDOWN,
    DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    DEFAULT_FLEET_FAILURE_DELAY,
    DEFAULT_FLEET_ROTATING_START,
    DEFAULT_FLEET_SUCCESS_DELAY,
    DOMAIN,
    UPDATE_CHANNEL_DEVELOPMENT,
    UPDATE_CHANNEL_STABLE,
)
from custom_components.meshcore_noc.discovery import async_discover_repeaters
from custom_components.meshcore_noc.models import (
    DeviceType,
    DiscoveredSourceRepeater,
    MissingSourceInformation,
    SourceEntityMappings,
)

from .helpers import add_meshcore_entry, add_repeater


def _device(
    display_name: str,
    device_type: DeviceType,
    stable_id: str = "stable-device-id",
) -> DiscoveredSourceRepeater:
    """Build a presentation-only discovery record."""
    return DiscoveredSourceRepeater(
        stable_id=stable_id,
        display_name=display_name,
        device_registry_id="device-registry-id",
        meshcore_config_entry_id="meshcore-entry-id",
        entities=SourceEntityMappings(),
        missing=MissingSourceInformation(),
        device_type=device_type,
    )


async def test_setup_aborts_when_meshcore_absent(hass: HomeAssistant) -> None:
    """The UI flow must clearly require MeshCore first."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "meshcore_not_installed"


async def test_duplicate_setup_is_prevented(hass: HomeAssistant) -> None:
    """Only one MeshCore NOC entry is permitted."""
    add_meshcore_entry(hass)
    MockConfigEntry(domain=DOMAIN, title="MeshCore NOC").add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_discovered_repeaters_and_stable_ids_are_stored(
    hass: HomeAssistant,
) -> None:
    """The form displays discovery and persists stable IDs in options."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="stable-node-id",
        name="Friendly Repeater",
    )
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert form["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {CONF_MANAGED_REPEATER_IDS: ["stable-node-id"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_MANAGED_REPEATER_IDS] == ["stable-node-id"]
    assert result["options"][CONF_UPDATE_CHANNEL] == UPDATE_CHANNEL_STABLE
    assert result["options"][CONF_CLOCK_CHECK_COOLDOWN] == DEFAULT_CLOCK_CHECK_COOLDOWN
    assert (
        result["options"][CONF_AUTO_FLEET_CLOCK_CHECKS]
        is DEFAULT_AUTO_FLEET_CLOCK_CHECKS
    )
    assert (
        result["options"][CONF_FLEET_CLOCK_INTERVAL_HOURS]
        == DEFAULT_FLEET_CLOCK_INTERVAL_HOURS
    )
    assert result["options"][CONF_FLEET_SUCCESS_DELAY] == DEFAULT_FLEET_SUCCESS_DELAY
    assert result["options"][CONF_FLEET_FAILURE_DELAY] == DEFAULT_FLEET_FAILURE_DELAY
    assert result["options"][CONF_FLEET_ROTATING_START] is DEFAULT_FLEET_ROTATING_START
    assert "Friendly Repeater" not in result["options"][CONF_MANAGED_REPEATER_IDS]


async def test_options_flow_updates_managed_repeaters(
    hass: HomeAssistant,
) -> None:
    """Options must replace only the NOC-owned stable-ID selection."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a", name="Node A")
    add_repeater(hass, meshcore_entry, stable_id="node-b", name="Node B")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a"]},
    )
    noc_entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(noc_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {CONF_MANAGED_REPEATER_IDS: ["node-b"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MANAGED_REPEATER_IDS] == ["node-b"]
    assert result["data"][CONF_UPDATE_CHANNEL] == UPDATE_CHANNEL_STABLE
    assert result["data"][CONF_CLOCK_CHECK_COOLDOWN] == DEFAULT_CLOCK_CHECK_COOLDOWN


async def test_options_flow_persists_development_channel(
    hass: HomeAssistant,
) -> None:
    """Selecting development persists beside the managed repeater selection."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a", name="Node A")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={
            CONF_MANAGED_REPEATER_IDS: ["node-a"],
            CONF_UPDATE_CHANNEL: UPDATE_CHANNEL_STABLE,
        },
    )
    noc_entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(noc_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            CONF_MANAGED_REPEATER_IDS: ["node-a"],
            CONF_UPDATE_CHANNEL: UPDATE_CHANNEL_DEVELOPMENT,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPDATE_CHANNEL] == UPDATE_CHANNEL_DEVELOPMENT


async def test_options_flow_persists_clock_check_cooldown(
    hass: HomeAssistant,
) -> None:
    """Manual clock cooldown is configurable within conservative bounds."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a", name="Node A")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a"]},
    )
    noc_entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(noc_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            CONF_MANAGED_REPEATER_IDS: ["node-a"],
            CONF_CLOCK_CHECK_COOLDOWN: 600,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CLOCK_CHECK_COOLDOWN] == 600


async def test_options_flow_persists_fleet_clock_configuration(
    hass: HomeAssistant,
) -> None:
    """Fleet scheduling, delays, and rotation persist together."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a"]},
    )
    noc_entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(noc_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            CONF_MANAGED_REPEATER_IDS: ["node-a"],
            CONF_AUTO_FLEET_CLOCK_CHECKS: True,
            CONF_FLEET_CLOCK_INTERVAL_HOURS: 12,
            CONF_FLEET_SUCCESS_DELAY: 20,
            CONF_FLEET_FAILURE_DELAY: 45,
            CONF_FLEET_ROTATING_START: True,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_FLEET_CLOCK_CHECKS] is True
    assert result["data"][CONF_FLEET_CLOCK_INTERVAL_HOURS] == 12
    assert result["data"][CONF_FLEET_SUCCESS_DELAY] == 20
    assert result["data"][CONF_FLEET_FAILURE_DELAY] == 45
    assert result["data"][CONF_FLEET_ROTATING_START] is True


async def test_options_flow_rejects_unsafe_fleet_clock_timing(
    hass: HomeAssistant,
) -> None:
    """Fleet timing values outside selector bounds cannot be persisted."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a"]},
    )
    noc_entry.add_to_hass(hass)

    form = await hass.config_entries.options.async_init(noc_entry.entry_id)
    with pytest.raises(InvalidData, match="Schema validation failed"):
        await hass.config_entries.options.async_configure(
            form["flow_id"],
            {
                CONF_MANAGED_REPEATER_IDS: ["node-a"],
                CONF_FLEET_CLOCK_INTERVAL_HOURS: 999,
            },
        )


async def test_device_labels_show_type_without_changing_stable_id(
    hass: HomeAssistant,
) -> None:
    """Presentation labels distinguish clients while IDs remain untouched."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="client-stable-id",
        name="Jaco",
        model="MeshCore Client",
    )
    discovery = await async_discover_repeaters(hass)
    device = discovery.repeaters["client-stable-id"]

    assert _device_label(device) == "📱 Jaco"
    assert device.stable_id == "client-stable-id"


def test_repeater_label_is_simplified() -> None:
    """Repeater labels contain only the icon and normalized friendly name."""
    device = _device(
        "MeshCore Repeater: Laguna2 (034bdb)",
        DeviceType.REPEATER,
    )

    assert _device_label(device) == "📡 Laguna2"


def test_client_label_is_simplified() -> None:
    """Client labels contain only the icon and normalized friendly name."""
    device = _device("MeshCore Client: Jaco (a2a812)", DeviceType.CLIENT)

    assert _device_label(device) == "📱 Jaco"


def test_unknown_label_uses_unknown_icon() -> None:
    """Unknown devices retain their friendly name with the unknown icon."""
    device = _device("MeshCore Arlo (c01509)", DeviceType.UNKNOWN)

    assert _device_label(device) == "❔ Arlo"


def test_ui_name_normalization_preserves_case_and_trims_whitespace() -> None:
    """Only recognized UI decoration is removed from friendly names."""
    assert (
        _ui_display_name("  MeshCore   Promicro Test Repeater   (c01509)  ", "id")
        == "Promicro Test Repeater"
    )


def test_selector_values_remain_stable_ids() -> None:
    """UI label normalization must not alter selector option values."""
    options = _selection_options(
        {
            "034bdb9383": _device(
                "MeshCore Repeater: Myburgh Park (034bdb)",
                DeviceType.REPEATER,
                stable_id="034bdb9383",
            ),
            "a2a812ff00": _device(
                "MeshCore Client: Arlo (a2a812)",
                DeviceType.CLIENT,
                stable_id="a2a812ff00",
            ),
        }
    )

    assert options == [
        {"value": "034bdb9383", "label": "📡 Myburgh Park"},
        {"value": "a2a812ff00", "label": "📱 Arlo"},
    ]


def test_only_validated_entity_platforms_are_present() -> None:
    """Phase 2 adds only the planned fleet button platform."""
    integration_dir = Path("custom_components/meshcore_noc")
    names = {path.name for path in integration_dir.iterdir()}

    assert {"sensor.py", "binary_sensor.py", "button.py"} <= names
    assert "number.py" not in names
