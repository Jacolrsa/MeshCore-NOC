"""Tests for non-destructive integration lifecycle."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshcore_noc.const import CONF_MANAGED_REPEATER_IDS, DOMAIN
from custom_components.meshcore_noc.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .helpers import add_meshcore_entry, add_repeater, setup_noc_entry, unload_noc_entry


async def test_setup_restores_managed_selection(hass: HomeAssistant) -> None:
    """Config entry options restore the stable-ID selection after load."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-persisted")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-persisted"]},
    )
    noc_entry.add_to_hass(hass)

    await setup_noc_entry(hass, noc_entry)
    assert len(noc_entry.runtime_data.coordinators) == 1
    assert noc_entry.runtime_data.coordinator is not None
    assert noc_entry.runtime_data.coordinator.source.stable_id == "node-persisted"


async def test_setup_restores_every_managed_selection(hass: HomeAssistant) -> None:
    """Every selected stable ID receives one coordinator in selection order."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a", name="Node A")
    add_repeater(hass, meshcore_entry, stable_id="node-b", name="Node B")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a", "node-b"]},
    )
    noc_entry.add_to_hass(hass)

    await setup_noc_entry(hass, noc_entry)
    assert [
        coordinator.source.stable_id
        for coordinator in noc_entry.runtime_data.coordinators
    ] == ["node-a", "node-b"]
    assert all(
        coordinator.source_listener_registered
        for coordinator in noc_entry.runtime_data.coordinators
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    assert diagnostics["configured_managed_repeater_count"] == 2
    assert diagnostics["active_managed_repeater_count"] == 2
    assert diagnostics["unresolved_managed_repeater_ids"] == []
    assert {managed["stable_id"] for managed in diagnostics["managed_devices"]} == {
        "node-a",
        "node-b",
    }


async def test_unload_does_not_change_meshcore_registry(
    hass: HomeAssistant,
) -> None:
    """Unloading NOC must not remove or modify MeshCore registry records."""
    meshcore_entry = add_meshcore_entry(hass)
    device, entities = add_repeater(hass, meshcore_entry)
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-123"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)
    dashboard_marker = object()
    hass.data["meshcore_noc_dashboard_marker"] = dashboard_marker

    before_device = dr.async_get(hass).async_get(device.id)
    before_entities = {
        entity_id: er.async_get(hass).async_get(entity_id)
        for entity_id in entities.values()
    }

    coordinators = noc_entry.runtime_data.coordinators
    await unload_noc_entry(hass, noc_entry)
    assert all(
        not coordinator.source_listener_registered for coordinator in coordinators
    )
    assert dr.async_get(hass).async_get(device.id) == before_device
    assert {
        entity_id: er.async_get(hass).async_get(entity_id)
        for entity_id in entities.values()
    } == before_entities
    assert hass.data["meshcore_noc_dashboard_marker"] is dashboard_marker


async def test_diagnostics_explain_device_classification(
    hass: HomeAssistant,
) -> None:
    """Diagnostics include per-type totals and mapping confidence."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="repeater-1",
        name="MeshCore Repeater: Laguna2 (034bdb)",
        model="MeshCore Repeater",
    )
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="client-1",
        name="Jaco",
        model="MeshCore Client",
    )
    noc_entry = MockConfigEntry(domain=DOMAIN, title="MeshCore NOC")
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)

    assert diagnostics["repeaters_discovered"] == 1
    assert diagnostics["clients_discovered"] == 1
    assert diagnostics["unknown_devices"] == 0
    assert diagnostics["managed_devices"] == []
    assert all("mapping_method" in device for device in diagnostics["repeaters"])
    assert all("confidence_score" in device for device in diagnostics["repeaters"])
    assert all("source_entity_count" in device for device in diagnostics["repeaters"])
    repeater = next(
        device
        for device in diagnostics["repeaters"]
        if device["stable_id"] == "repeater-1"
    )
    assert repeater["display_name"] == "MeshCore Repeater: Laguna2 (034bdb)"
    assert repeater["stable_id"] == "repeater-1"


async def test_options_reload_reconciles_deselection_and_reselection(
    hass: HomeAssistant,
) -> None:
    """Options changes remove and recreate exactly one managed identity."""
    meshcore_entry = add_meshcore_entry(hass)
    upstream_devices = {}
    for stable_id in ("node-a", "node-b", "node-c"):
        upstream_devices[stable_id], _ = add_repeater(
            hass,
            meshcore_entry,
            stable_id=stable_id,
            name=f"MeshCore Repeater: {stable_id} (abcdef)",
        )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a", "node-b", "node-c"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    original = {
        coordinator.source.stable_id: coordinator
        for coordinator in noc_entry.runtime_data.coordinators
    }
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    controller = device_registry.async_get_device(identifiers={(DOMAIN, "noc")})
    removed_device = device_registry.async_get_device(identifiers={(DOMAIN, "node-b")})
    retained_device = device_registry.async_get_device(identifiers={(DOMAIN, "node-a")})
    assert controller is not None
    assert removed_device is not None
    assert retained_device is not None
    retained_entity_ids = {
        registry_entry.entity_id
        for registry_entry in er.async_entries_for_device(
            entity_registry,
            retained_device.id,
            include_disabled_entities=True,
        )
        if registry_entry.platform == DOMAIN
    }

    hass.config_entries.async_update_entry(
        noc_entry,
        options={CONF_MANAGED_REPEATER_IDS: ["node-a", "node-c"]},
    )
    await hass.async_block_till_done()

    assert not original["node-b"].source_listener_registered
    assert {
        coordinator.source.stable_id
        for coordinator in noc_entry.runtime_data.coordinators
    } == {"node-a", "node-c"}
    assert all(
        coordinator.source_listener_registered
        for coordinator in noc_entry.runtime_data.coordinators
    )
    assert not er.async_entries_for_device(
        entity_registry,
        removed_device.id,
        include_disabled_entities=True,
    )
    assert device_registry.async_get(removed_device.id) is None
    assert device_registry.async_get(controller.id) is not None
    assert device_registry.async_get(upstream_devices["node-b"].id) is not None
    assert {
        registry_entry.entity_id
        for registry_entry in er.async_entries_for_device(
            entity_registry,
            retained_device.id,
            include_disabled_entities=True,
        )
        if registry_entry.platform == DOMAIN
    } == retained_entity_ids
    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    assert diagnostics["reconciliation"] == {
        "created": [],
        "retained": ["node-a", "node-c"],
        "removed": ["node-b"],
    }

    hass.config_entries.async_update_entry(
        noc_entry,
        options={CONF_MANAGED_REPEATER_IDS: ["node-c", "node-b", "node-a"]},
    )
    await hass.async_block_till_done()

    active = [
        coordinator
        for coordinator in noc_entry.runtime_data.coordinators
        if coordinator.source.stable_id == "node-b"
    ]
    assert len(active) == 1
    assert active[0].source_listener_registered
    recreated = device_registry.async_get_device(identifiers={(DOMAIN, "node-b")})
    assert recreated is not None
    recreated_entries = [
        entry
        for entry in er.async_entries_for_device(
            entity_registry,
            recreated.id,
            include_disabled_entities=True,
        )
        if entry.platform == DOMAIN
    ]
    assert len(recreated_entries) == 5
    assert len({entry.unique_id for entry in recreated_entries}) == 5
    assert (
        sum(
            (DOMAIN, "node-b") in device.identifiers
            for device in device_registry.devices.values()
        )
        == 1
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    assert diagnostics["reconciliation"] == {
        "created": ["node-b"],
        "retained": ["node-a", "node-c"],
        "removed": [],
    }
    assert not diagnostics["duplicate_detection"]["duplicates_detected"]

    coordinators = noc_entry.runtime_data.coordinators
    await unload_noc_entry(hass, noc_entry)
    assert all(
        not coordinator.source_listener_registered for coordinator in coordinators
    )


async def test_empty_selection_removes_stale_config_entry_registry_records(
    hass: HomeAssistant,
) -> None:
    """Real registry records survive config-entry replacement but not deselection."""
    meshcore_entry = add_meshcore_entry(hass)
    upstream_device, upstream_entities = add_repeater(
        hass,
        meshcore_entry,
        stable_id="test-solar-stable-id",
        name="Test Solar",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["test-solar-stable-id"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    managed_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "test-solar-stable-id")}
    )
    assert managed_device is not None
    managed_entries = [
        entity_entry
        for entity_entry in er.async_entries_for_device(
            entity_registry,
            managed_device.id,
            include_disabled_entities=True,
        )
        if entity_entry.platform == DOMAIN
    ]
    assert len(managed_entries) == 5
    assert {entity_entry.unique_id for entity_entry in managed_entries} == {
        "promicro_repeater_calibrated_voltage",
        "promicro_repeater_calibrated_battery_percentage",
        "promicro_repeater_health",
        "promicro_repeater_fresh",
        "promicro_repeater_check_clock",
    }

    # Model records retained from a previous NOC config-entry instance. This is
    # supported by the real registry API but was absent from the Alpha3.1 test.
    stale_config_entry_id = "previous-meshcore-noc-config-entry"
    for entity_entry in managed_entries:
        entity_registry.async_update_entity(
            entity_entry.entity_id,
            config_entry_id=stale_config_entry_id,
        )

    template_entry = entity_registry.async_get_or_create(
        domain="sensor",
        platform="template",
        unique_id="user-template-battery",
        original_name="User Template Battery",
    )
    input_number_entry = entity_registry.async_get_or_create(
        domain="input_number",
        platform="input_number",
        unique_id="user-battery-calibration",
        original_name="User Battery Calibration",
    )
    hass.states.async_set(template_entry.entity_id, "75")
    hass.states.async_set(input_number_entry.entity_id, "3.2")

    hass.config_entries.async_update_entry(
        noc_entry,
        options={CONF_MANAGED_REPEATER_IDS: []},
    )
    await hass.async_block_till_done()

    for entity_entry in managed_entries:
        assert entity_registry.async_get(entity_entry.entity_id) is None
    assert device_registry.async_get(managed_device.id) is None
    assert entity_registry.async_get(template_entry.entity_id) is not None
    assert entity_registry.async_get(input_number_entry.entity_id) is not None
    assert device_registry.async_get(upstream_device.id) is not None
    assert all(
        entity_registry.async_get(entity_id) is not None
        for entity_id in upstream_entities.values()
    )

    hass.config_entries.async_update_entry(
        noc_entry,
        options={CONF_MANAGED_REPEATER_IDS: ["test-solar-stable-id"]},
    )
    await hass.async_block_till_done()

    recreated_devices = [
        device
        for device in device_registry.devices.values()
        if (DOMAIN, "test-solar-stable-id") in device.identifiers
    ]
    assert len(recreated_devices) == 1
    recreated_entries = [
        entity_entry
        for entity_entry in er.async_entries_for_device(
            entity_registry,
            recreated_devices[0].id,
            include_disabled_entities=True,
        )
        if entity_entry.platform == DOMAIN
    ]
    assert len(recreated_entries) == 5
    assert len({entity_entry.unique_id for entity_entry in recreated_entries}) == 5
