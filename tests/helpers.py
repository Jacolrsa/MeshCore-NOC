"""Registry helpers for MeshCore NOC tests."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def setup_noc_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up a NOC entry through Home Assistant's real lifecycle."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def unload_noc_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Unload a NOC entry through Home Assistant's real lifecycle."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def add_meshcore_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a configured MeshCore source integration."""
    entry = MockConfigEntry(domain="meshcore", title="MeshCore")
    entry.add_to_hass(hass)
    return entry


def add_repeater(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    stable_id: str = "node-123",
    name: str = "Hilltop Repeater",
    model: str | None = None,
    sources: tuple[str, ...] = ("voltage", "battery", "airtime", "availability"),
    state: str = "1",
    public_key: str | None = None,
    pubkey_prefix: str | None = None,
    contact_pubkey_prefix: str | None = None,
) -> tuple[Any, dict[str, str]]:
    """Add a MeshCore-owned device and optional source entities."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("meshcore", stable_id)},
        name=name,
        model=model,
    )
    entity_ids: dict[str, str] = {}
    definitions = {
        "voltage": ("voltage", "V"),
        "battery": ("battery", "%"),
        "airtime": (None, "%"),
        "availability": (None, None),
    }
    for role in sources:
        device_class, unit = definitions[role]
        registry_entry = entity_registry.async_get_or_create(
            domain="sensor" if role != "availability" else "binary_sensor",
            platform="meshcore",
            unique_id=f"{stable_id}-{role}",
            config_entry=entry,
            device_id=device.id,
            original_name=role.replace("_", " ").title(),
        )
        attributes = {}
        if device_class:
            attributes["device_class"] = device_class
        if unit:
            attributes["unit_of_measurement"] = unit
        if public_key:
            attributes["public_key"] = public_key
        if pubkey_prefix:
            attributes["pubkey_prefix"] = pubkey_prefix
        hass.states.async_set(registry_entry.entity_id, state, attributes)
        entity_ids[role] = registry_entry.entity_id
    if contact_pubkey_prefix:
        contact = entity_registry.async_get_or_create(
            domain="sensor",
            platform="meshcore",
            unique_id=f"{stable_id}-contact",
            config_entry=entry,
            device_id=device.id,
            original_name="Contact metadata",
        )
        hass.states.async_set(
            contact.entity_id,
            "available",
            {"pubkey_prefix": contact_pubkey_prefix},
        )
        entity_ids["contact"] = contact.entity_id
    return device, entity_ids
