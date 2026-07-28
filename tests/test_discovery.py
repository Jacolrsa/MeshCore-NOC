"""Tests for defensive MeshCore registry discovery."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.meshcore_noc.discovery import (
    async_discover_repeaters,
    classify_source_role,
)
from custom_components.meshcore_noc.models import DeviceType

from .helpers import add_meshcore_entry, add_repeater


async def test_incomplete_telemetry_remains_discoverable(
    hass: HomeAssistant,
) -> None:
    """Missing optional sources must be reported, not exclude a repeater."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, sources=("voltage",))

    result = await async_discover_repeaters(hass)

    assert set(result.repeaters) == {"node-123"}
    assert "battery_percentage" in result.repeaters["node-123"].missing.roles
    assert "airtime_utilisation" in result.repeaters["node-123"].missing.roles
    assert result.repeaters["node-123"].warnings == ()


async def test_no_telemetry_remains_discoverable(hass: HomeAssistant) -> None:
    """A stable MeshCore-owned device remains visible with no source entities."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, sources=())

    result = await async_discover_repeaters(hass)

    assert set(result.repeaters) == {"node-123"}
    assert len(result.repeaters["node-123"].missing.roles) == 4


async def test_unavailable_source_is_not_removed(hass: HomeAssistant) -> None:
    """Unavailable state changes availability, not registry membership."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, state="unavailable")

    result = await async_discover_repeaters(hass)

    assert set(result.repeaters) == {"node-123"}
    assert result.repeaters["node-123"].stable_id == "node-123"


async def test_friendly_name_is_not_identity(hass: HomeAssistant) -> None:
    """Stable MeshCore device identifiers must be used as primary keys."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="stable-node-id",
        name="Changeable Friendly Name",
    )

    result = await async_discover_repeaters(hass)

    assert "stable-node-id" in result.repeaters
    assert "Changeable Friendly Name" not in result.repeaters


async def test_raw_stable_id_is_exact_command_prefix(hass: HomeAssistant) -> None:
    """A current MeshCore 12-hex stable ID remains untruncated and routable."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="01c1a4fa32c6",
        name="Laguna2",
        model="MeshCore Repeater",
    )

    result = await async_discover_repeaters(hass)

    repeater = result.repeaters["01c1a4fa32c6"]
    assert repeater.stable_id == "01c1a4fa32c6"
    assert repeater.pubkey_prefix == "01c1a4fa32c6"


async def test_full_public_key_maps_to_exact_twelve_character_prefix(
    hass: HomeAssistant,
) -> None:
    """The full key is distinct metadata and maps to MeshCore's exact prefix."""
    meshcore_entry = add_meshcore_entry(hass)
    public_key = "01c1a4fa32c6" + ("ab" * 26)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="opaque-noc-id",
        model="MeshCore Repeater",
        public_key=public_key,
    )

    result = await async_discover_repeaters(hass)

    repeater = result.repeaters["opaque-noc-id"]
    assert repeater.public_key == public_key
    assert repeater.pubkey_prefix == "01c1a4fa32c6"


async def test_legacy_full_key_identifier_maps_without_prefix_overrun(
    hass: HomeAssistant,
) -> None:
    """A legacy composite full-key identifier dispatches only its 12-char prefix."""
    meshcore_entry = add_meshcore_entry(hass)
    public_key = "01c1a4fa32c6" + ("cd" * 26)
    stable_id = f"{meshcore_entry.entry_id}_repeater_{public_key}"
    add_repeater(
        hass,
        meshcore_entry,
        stable_id=stable_id,
        model="MeshCore Repeater",
    )

    repeater = (await async_discover_repeaters(hass)).repeaters[stable_id]

    assert repeater.public_key == public_key
    assert repeater.pubkey_prefix == "01c1a4fa32c6"


async def test_generated_stable_id_resolves_device_identifier(
    hass: HomeAssistant,
) -> None:
    """An integration-generated repeater ID resolves without entry-ID assumptions."""
    meshcore_entry = add_meshcore_entry(hass)
    stable_id = f"{meshcore_entry.entry_id}_repeater_112233445566"
    add_repeater(
        hass,
        meshcore_entry,
        stable_id=stable_id,
        model="MeshCore Repeater",
    )

    repeater = (await async_discover_repeaters(hass)).repeaters[stable_id]

    assert repeater.pubkey_prefix == "112233445566"
    assert repeater.command_address.resolution_source == "device_identifier"


async def test_contact_entity_pubkey_prefix_metadata_is_resolved(
    hass: HomeAssistant,
) -> None:
    """Contact metadata addresses an unusual opaque managed stable ID."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="opaque-laguna-record",
        name="Laguna2",
        model="MeshCore Repeater",
        contact_pubkey_prefix="01c1a4fa32c6",
    )

    repeater = (await async_discover_repeaters(hass)).repeaters["opaque-laguna-record"]

    assert repeater.pubkey_prefix == "01c1a4fa32c6"
    assert repeater.command_address.resolution_source == "contact_entity_pubkey_prefix"


async def test_explicit_prefix_has_priority_over_conflicting_legacy_id(
    hass: HomeAssistant,
) -> None:
    """Lower-priority legacy text cannot invalidate explicit MeshCore metadata."""
    meshcore_entry = add_meshcore_entry(hass)
    stable_id = "legacy_repeater_aaaaaaaaaaaa"
    add_repeater(
        hass,
        meshcore_entry,
        stable_id=stable_id,
        model="MeshCore Repeater",
        pubkey_prefix="01c1a4fa32c6",
    )

    repeater = (await async_discover_repeaters(hass)).repeaters[stable_id]

    assert repeater.pubkey_prefix == "01c1a4fa32c6"
    assert repeater.command_address.resolution_source == "explicit_pubkey_prefix"


async def test_legacy_stable_id_is_final_resolution_fallback(
    hass: HomeAssistant,
) -> None:
    """A legacy opaque ID with an embedded exact prefix remains addressable."""
    meshcore_entry = add_meshcore_entry(hass)
    stable_id = "legacy-node--01c1a4fa32c6--saved"
    add_repeater(
        hass,
        meshcore_entry,
        stable_id=stable_id,
        model="MeshCore Repeater",
        sources=(),
    )

    repeater = (await async_discover_repeaters(hass)).repeaters[stable_id]

    assert repeater.pubkey_prefix == "01c1a4fa32c6"
    assert repeater.command_address.resolution_source == "legacy_stable_id"


async def test_ambiguous_explicit_prefix_continues_to_device_identifier(
    hass: HomeAssistant,
) -> None:
    """Ambiguous high-priority evidence cannot block a later unique source."""
    meshcore_entry = add_meshcore_entry(hass)
    _device, entities = add_repeater(
        hass,
        meshcore_entry,
        stable_id="01c1a4fa32c6",
        model="MeshCore Repeater",
        pubkey_prefix="01c1a4fa32c6",
    )
    state = hass.states.get(entities["battery"])
    assert state is not None
    hass.states.async_set(
        entities["battery"],
        state.state,
        {**state.attributes, "pubkey_prefix": "112233445566"},
    )

    repeater = (await async_discover_repeaters(hass)).repeaters["01c1a4fa32c6"]

    assert repeater.pubkey_prefix == "01c1a4fa32c6"
    assert repeater.command_address.resolution_source == "device_identifier"
    assert repeater.command_address.resolution_sources_checked == (
        "explicit_pubkey_prefix",
        "full_public_key",
        "contact_entity_pubkey_prefix",
        "device_identifier",
    )


async def test_ambiguity_is_rejected_only_after_every_source_is_exhausted(
    hass: HomeAssistant,
) -> None:
    """Unresolved ambiguity is reported after checking every evidence level."""
    meshcore_entry = add_meshcore_entry(hass)
    _device, entities = add_repeater(
        hass,
        meshcore_entry,
        stable_id="opaque-managed-record",
        model="MeshCore Repeater",
        pubkey_prefix="01c1a4fa32c6",
    )
    state = hass.states.get(entities["battery"])
    assert state is not None
    hass.states.async_set(
        entities["battery"],
        state.state,
        {**state.attributes, "pubkey_prefix": "112233445566"},
    )

    repeater = (await async_discover_repeaters(hass)).repeaters["opaque-managed-record"]

    assert repeater.pubkey_prefix is None
    assert repeater.command_address.resolution_sources_checked == (
        "explicit_pubkey_prefix",
        "full_public_key",
        "contact_entity_pubkey_prefix",
        "device_identifier",
        "source_entity_identifier",
        "legacy_stable_id",
    )
    assert repeater.command_address.rejection_reason == (
        "no unique 12-character pubkey prefix found after all resolution "
        "sources; ambiguous explicit_pubkey_prefix: multiple 12-character "
        "pubkey prefixes"
    )


async def test_missing_prefix_records_resolution_diagnostics(
    hass: HomeAssistant,
) -> None:
    """An unaddressable managed shape retains every checked evidence source."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="unusual-stable-id",
        model="MeshCore Repeater",
        sources=(),
    )

    repeater = (await async_discover_repeaters(hass)).repeaters["unusual-stable-id"]

    assert repeater.pubkey_prefix is None
    assert repeater.command_address.resolution_sources_checked == (
        "explicit_pubkey_prefix",
        "full_public_key",
        "contact_entity_pubkey_prefix",
        "device_identifier",
        "source_entity_identifier",
        "legacy_stable_id",
    )
    assert repeater.command_address.rejection_reason == (
        "no valid 12-character pubkey prefix found"
    )


async def test_device_type_prefers_registry_metadata(hass: HomeAssistant) -> None:
    """Structured device metadata classifies repeaters ahead of mutable names."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="client-looking-name",
        name="Client-looking name",
        model="MeshCore Repeater",
    )

    result = await async_discover_repeaters(hass)
    device = result.repeaters["client-looking-name"]

    assert device.device_type is DeviceType.REPEATER
    assert device.device_type_method == "device_registry_metadata"


async def test_clients_remain_discoverable(hass: HomeAssistant) -> None:
    """Client devices remain selectable discovery records."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="client-123",
        name="Jaco",
        model="MeshCore Client",
    )

    result = await async_discover_repeaters(hass)

    assert result.repeaters["client-123"].device_type is DeviceType.CLIENT


async def test_exact_unique_id_removes_duplicate_voltage_warning(
    hass: HomeAssistant,
) -> None:
    """An exact unique-ID role must beat a generic device-class candidate."""
    meshcore_entry = add_meshcore_entry(hass)
    device, entities = add_repeater(
        hass,
        meshcore_entry,
        sources=("voltage",),
    )
    entity_registry = er.async_get(hass)
    backup = entity_registry.async_get_or_create(
        domain="sensor",
        platform="meshcore",
        unique_id="node-123-backup-reading",
        config_entry=meshcore_entry,
        device_id=device.id,
        original_name="Backup reading",
    )
    hass.states.async_set(
        backup.entity_id,
        "4.1",
        {"device_class": "voltage", "unit_of_measurement": "V"},
    )

    result = await async_discover_repeaters(hass)
    discovered = result.repeaters["node-123"]

    assert discovered.entities.voltage == entities["voltage"]
    assert not any("voltage mapping" in warning for warning in discovered.warnings)


def test_middle_unique_id_role_token_is_a_safe_fallback() -> None:
    """Legacy MeshCore IDs may place a bounded role token before the name."""
    role = classify_source_role(
        entity_id="sensor.meshcore_034bdb9383_bat_promicro_repeater",
        unique_id="meshcore_034bdb9383_bat_promicro_repeater",
        original_name="Promicro Repeater",
        translation_key=None,
        device_class=None,
        unit_of_measurement=None,
    )

    assert role == "voltage"
