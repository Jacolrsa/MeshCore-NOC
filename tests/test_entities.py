"""Tests for the alpha2 managed-device entities."""

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshcore_noc.const import (
    CONF_MANAGED_REPEATER_IDS,
    DOMAIN,
    INTEGRATION_VERSION,
)
from custom_components.meshcore_noc.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .helpers import add_meshcore_entry, add_repeater, setup_noc_entry, unload_noc_entry


def _state(hass: HomeAssistant, entity_id: str) -> State:
    """Return one required test state."""
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def test_all_selected_repeaters_create_entities_and_preserve_alpha2_identity(
    hass: HomeAssistant,
) -> None:
    """Alpha3 instantiates all selections without changing Alpha2 identities."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="promicro-stable-id",
        name="ProMicro Repeater",
        state="4.016",
    )
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="laguna-stable-id",
        name="MeshCore Repeater: Laguna2 (034bdb)",
        state="4.216",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={
            CONF_MANAGED_REPEATER_IDS: [
                "promicro-stable-id",
                "laguna-stable-id",
            ]
        },
    )
    noc_entry.add_to_hass(hass)
    wrongly_named_laguna = dr.async_get(hass).async_get_or_create(
        config_entry_id=noc_entry.entry_id,
        identifiers={(DOMAIN, "laguna-stable-id")},
        name="ProMicro Repeater",
    )

    await setup_noc_entry(hass, noc_entry)

    expected = {
        "sensor.meshcore_noc_promicro_repeater_calibrated_voltage",
        "sensor.meshcore_noc_promicro_repeater_calibrated_battery_percentage",
        "sensor.meshcore_noc_promicro_repeater_health",
        "binary_sensor.meshcore_noc_promicro_repeater_fresh",
        "sensor.meshcore_noc_laguna2_calibrated_voltage",
        "sensor.meshcore_noc_laguna2_calibrated_battery_percentage",
        "sensor.meshcore_noc_laguna2_health",
        "binary_sensor.meshcore_noc_laguna2_fresh",
    }
    noc_entities = {
        entity_id
        for entity_id in hass.states.async_entity_ids()
        if entity_id.split(".", 1)[0] in {"sensor", "binary_sensor"}
        and entity_id.split(".", 1)[1].startswith("meshcore_noc_")
    }
    assert noc_entities == expected
    assert (
        _state(hass, "sensor.meshcore_noc_promicro_repeater_calibrated_voltage").state
        == "3.2"
    )
    assert (
        _state(
            hass,
            "sensor.meshcore_noc_promicro_repeater_calibrated_battery_percentage",
        ).state
        == "17"
    )
    assert _state(hass, "sensor.meshcore_noc_promicro_repeater_health").state == "Poor"
    assert (
        _state(hass, "binary_sensor.meshcore_noc_promicro_repeater_fresh").state == "on"
    )
    assert _state(hass, "sensor.meshcore_noc_laguna2_calibrated_voltage").state == "3.4"
    assert (
        _state(hass, "sensor.meshcore_noc_laguna2_calibrated_battery_percentage").state
        == "33"
    )

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    parent = device_registry.async_get_device(identifiers={(DOMAIN, "noc")})
    child = device_registry.async_get_device(
        identifiers={(DOMAIN, "promicro-stable-id")}
    )
    laguna = device_registry.async_get_device(
        identifiers={(DOMAIN, "laguna-stable-id")}
    )
    assert parent is not None
    assert parent.name == "MeshCore NOC"
    assert child is not None
    assert child.name == "ProMicro Repeater"
    assert child.model == "MeshCore NOC Managed Repeater"
    assert child.via_device_id == parent.id
    assert laguna is not None
    assert laguna.id == wrongly_named_laguna.id
    assert laguna.name == "Laguna2"
    assert laguna.model == "MeshCore NOC Managed Repeater"
    assert laguna.via_device_id == parent.id
    assert (
        len(
            [
                device
                for device in device_registry.devices.values()
                if (DOMAIN, "promicro-stable-id") in device.identifiers
            ]
        )
        == 1
    )

    expected_names = {
        "sensor.meshcore_noc_promicro_repeater_calibrated_voltage": (
            "Calibrated Voltage"
        ),
        "sensor.meshcore_noc_promicro_repeater_calibrated_battery_percentage": (
            "Calibrated Battery"
        ),
        "sensor.meshcore_noc_promicro_repeater_health": "Health",
        "binary_sensor.meshcore_noc_promicro_repeater_fresh": "Freshness",
    }
    for entity_id, name in expected_names.items():
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.original_name == name
        assert registry_entry.device_id == child.id

    voltage = _state(hass, "sensor.meshcore_noc_promicro_repeater_calibrated_voltage")
    battery = _state(
        hass,
        "sensor.meshcore_noc_promicro_repeater_calibrated_battery_percentage",
    )
    health = _state(hass, "sensor.meshcore_noc_promicro_repeater_health")
    assert voltage.attributes["device_class"] == "voltage"
    assert voltage.attributes["unit_of_measurement"] == "V"
    assert voltage.attributes["state_class"] == "measurement"
    assert battery.attributes["device_class"] == "battery"
    assert battery.attributes["unit_of_measurement"] == "%"
    assert battery.attributes["state_class"] == "measurement"
    assert "state_class" not in health.attributes

    voltage_entry = entity_registry.async_get(voltage.entity_id)
    battery_entry = entity_registry.async_get(battery.entity_id)
    assert voltage_entry is not None
    assert battery_entry is not None
    assert voltage_entry.options["sensor"]["suggested_display_precision"] == 3
    assert battery_entry.options["sensor"]["suggested_display_precision"] == 0

    laguna_voltage = entity_registry.async_get(
        "sensor.meshcore_noc_laguna2_calibrated_voltage"
    )
    assert laguna_voltage is not None
    assert (
        laguna_voltage.unique_id
        == "managed_repeater_laguna-stable-id_calibrated_voltage"
    )
    assert laguna_voltage.device_id == laguna.id


async def test_source_change_updates_immediately_and_listener_unloads(
    hass: HomeAssistant,
) -> None:
    """A source event refreshes all entities and unload removes its listener."""
    meshcore_entry = add_meshcore_entry(hass)
    _, entities = add_repeater(
        hass,
        meshcore_entry,
        stable_id="promicro-stable-id",
        name="ProMicro Repeater",
        state="4.016",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["promicro-stable-id"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    coordinator = noc_entry.runtime_data.coordinator
    assert coordinator is not None
    assert coordinator.source_listener_registered

    hass.states.async_set(entities["voltage"], "4.216")
    await hass.async_block_till_done()

    assert (
        _state(hass, "sensor.meshcore_noc_promicro_repeater_calibrated_voltage").state
        == "3.4"
    )
    assert (
        _state(
            hass,
            "sensor.meshcore_noc_promicro_repeater_calibrated_battery_percentage",
        ).state
        == "33"
    )

    await unload_noc_entry(hass, noc_entry)
    assert not coordinator.source_listener_registered


async def test_alpha2_identity_stays_with_existing_device_after_reorder(
    hass: HomeAssistant,
) -> None:
    """Selection reordering must not move Alpha2 IDs to another repeater."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="original-alpha2-device",
        name="ProMicro Repeater",
    )
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="new-alpha3-device",
        name="MeshCore Repeater: Hilltop (a1b2c3)",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["original-alpha2-device"]},
    )
    noc_entry.add_to_hass(hass)

    await setup_noc_entry(hass, noc_entry)
    await unload_noc_entry(hass, noc_entry)

    hass.config_entries.async_update_entry(
        noc_entry,
        options={
            CONF_MANAGED_REPEATER_IDS: [
                "new-alpha3-device",
                "original-alpha2-device",
            ]
        },
    )
    await setup_noc_entry(hass, noc_entry)

    legacy = next(
        coordinator
        for coordinator in noc_entry.runtime_data.coordinators
        if coordinator.legacy_identity
    )
    assert legacy.source.stable_id == "original-alpha2-device"

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    legacy_entity = entity_registry.async_get(
        "sensor.meshcore_noc_promicro_repeater_calibrated_voltage"
    )
    legacy_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "original-alpha2-device")}
    )
    assert legacy_entity is not None
    assert legacy_device is not None
    assert legacy_entity.device_id == legacy_device.id
    assert legacy_device.name == "ProMicro Repeater"
    new_device = device_registry.async_get_device(
        identifiers={(DOMAIN, "new-alpha3-device")}
    )
    assert new_device is not None
    assert new_device.name == "Hilltop"
    assert hass.states.get("sensor.meshcore_noc_hilltop_calibrated_voltage") is not None


async def test_unavailable_source_is_offline_and_unknown(
    hass: HomeAssistant,
) -> None:
    """A genuinely unavailable source retains Offline and Unknown semantics."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="promicro-stable-id",
        name="ProMicro Repeater",
        state="unavailable",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["promicro-stable-id"]},
    )
    noc_entry.add_to_hass(hass)

    await setup_noc_entry(hass, noc_entry)

    assert (
        _state(hass, "sensor.meshcore_noc_promicro_repeater_health").state == "Unknown"
    )
    freshness = _state(hass, "binary_sensor.meshcore_noc_promicro_repeater_fresh")
    assert freshness.state == "off"
    assert freshness.attributes["freshness_status"] == "Offline"
    assert not freshness.attributes["source_available"]


async def test_diagnostics_include_alpha_2_1_runtime_fields(
    hass: HomeAssistant,
) -> None:
    """Diagnostics expose source, timing, listener, and calculated state."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(
        hass,
        meshcore_entry,
        stable_id="promicro-stable-id",
        name="ProMicro Repeater",
        state="4.016",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["promicro-stable-id"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    managed = diagnostics["managed_devices"][0]

    assert diagnostics["integration_version"] == INTEGRATION_VERSION
    assert managed["coordinator"]["last_successful_update"] is not None
    assert managed["coordinator"]["last_attempted_update"] is not None
    assert managed["coordinator"]["source_listener_registered"]
    assert managed["source"]["current_state"] == "4.016"
    assert managed["source"]["available"]
    assert managed["source"]["last_changed"] is not None
    assert managed["source"]["last_updated"] is not None
    assert managed["calculated_values"]["calibrated_voltage"] == 3.2
    assert managed["calculated_values"]["battery_percentage"] == 17
    assert managed["freshness"]["status"] == "Fresh"
    assert managed["freshness"]["age_seconds"] is not None
    assert managed["freshness"]["next_expected_transition"] is not None
    assert managed["health"] == "Poor"


async def test_managed_repeater_creates_clock_diagnostic_sensors(
    hass: HomeAssistant,
) -> None:
    """Addressable repeaters expose exactly offset and status diagnostics."""
    meshcore_entry = add_meshcore_entry(hass)
    stable_id = f"{meshcore_entry.entry_id}_repeater_a1b2c3d4e5f6"
    add_repeater(
        hass,
        meshcore_entry,
        stable_id=stable_id,
        name="Clock Test",
        model="Mesh Repeater",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: [stable_id]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    offset = _state(hass, "sensor.meshcore_noc_promicro_repeater_clock_offset")
    status = _state(hass, "sensor.meshcore_noc_promicro_repeater_clock_status")
    progress = _state(hass, "sensor.clock_check_progress")
    fleet_state = _state(hass, "sensor.clock_check_state")
    last_fleet = _state(hass, "sensor.last_fleet_clock_check")
    fleet_running = _state(hass, "binary_sensor.clock_check_running")
    fleet_health = _state(hass, "sensor.fleet_clock_health")
    check_clock = _state(hass, "button.meshcore_noc_promicro_repeater_check_clock")
    check_all = _state(hass, "button.check_all_clocks")
    cancel = _state(hass, "button.cancel_clock_check")
    assert offset.state == "unknown"
    assert offset.attributes["unit_of_measurement"] == "s"
    assert offset.attributes["last_successful_clock_check"] is None
    assert offset.attributes["last_clock_attempt_outcome"] is None
    assert offset.attributes["clock_data_age_seconds"] is None
    assert status.state == "Unknown"
    assert status.attributes["request_state"] == "queued"
    assert progress.state == "0/0"
    assert fleet_state.state == "Idle"
    assert last_fleet.state == "unknown"
    assert fleet_running.state == "off"
    assert fleet_health.state == "Unknown"
    assert fleet_health.attributes["unknown"] == 1
    assert check_clock.state == "unknown"
    assert check_all.state == "unknown"
    assert cancel.state == "unavailable"

    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    clock = diagnostics["clock_intelligence"]
    assert clock["outstanding_requests"] == []
    assert clock["last_request"] is None
    assert clock["last_response"] is None
    assert clock["last_parse_result"] is None
    assert clock["last_timeout"] is None
    assert clock["history"] == []
    assert clock["fleet_health"]["unknown"] == 1
    assert clock["retained_results"][stable_id]["last_successful_clock_check"] is None
    assert clock["managed_repeaters_total"] == 1
    assert clock["addressable_repeaters_total"] == 1
    assert clock["non_addressable_repeaters"] == []
    assert clock["managed_repeater_addressability"] == [
        {
            "stable_id": stable_id,
            "friendly_name": "Clock Test",
            "device_type": "repeater",
            "resolution_source": "device_identifier",
            "pubkey_prefix": "a1b2c3d4e5f6",
            "resolution_sources_checked": [
                "explicit_pubkey_prefix",
                "full_public_key",
                "contact_entity_pubkey_prefix",
                "device_identifier",
            ],
            "accepted": True,
            "reason": (
                "accepted: managed device has one unique valid "
                "12-character pubkey_prefix"
            ),
        }
    ]
    assert clock["fleet"]["configuration"] == {
        "automatic_enabled": False,
        "interval_hours": 6,
        "success_delay_seconds": 15,
        "failure_delay_seconds": 30,
        "rotating_start": False,
    }
    assert clock["fleet"]["current_run"] is None
    assert clock["fleet"]["scheduler_state"] == "disabled"
    assert clock["fleet"]["next_scheduled_run"] is None
    assert clock["fleet"]["history"] == []
    assert clock["fleet"]["queue"] == []
    assert diagnostics["managed_devices"][0]["clock"]["clock_status"] == "UNKNOWN"


async def test_no_selection_preserves_alpha1_setup(hass: HomeAssistant) -> None:
    """An Alpha1 entry without selections remains valid and creates no entities."""
    add_meshcore_entry(hass)
    noc_entry = MockConfigEntry(domain=DOMAIN, title="MeshCore NOC")
    noc_entry.add_to_hass(hass)

    await setup_noc_entry(hass, noc_entry)

    assert noc_entry.runtime_data.coordinators == ()
    assert not any(
        entity_id.split(".", 1)[1].startswith("meshcore_noc_")
        and entity_id.split(".", 1)[0] in {"sensor", "binary_sensor"}
        for entity_id in hass.states.async_entity_ids()
    )


async def test_eight_repeaters_keep_their_own_normalized_names(
    hass: HomeAssistant,
) -> None:
    """Each stable repeater ID owns its discovered friendly name."""
    meshcore_entry = add_meshcore_entry(hass)
    repeaters = {
        "node-laguna": "MeshCore Repeater: Laguna2 (034bdb)",
        "node-myburgh": "MeshCore Repeater: Myburgh park (111111)",
        "node-promicro": "ProMicro Repeater",
        "node-promicro-test": "ProMicro test Repeater (222222)",
        "node-saldanha": "MeshCore Repeater: Saldanha (333333)",
        "node-solar": "Test Solar",
        "node-vredenburg": "MeshCore Repeater: Vredenburg (444444)",
        "node-vredenburg-ne": "Vredenburg NE (555555)",
    }
    expected_names = {
        "node-laguna": "Laguna2",
        "node-myburgh": "Myburgh park",
        "node-promicro": "ProMicro Repeater",
        "node-promicro-test": "ProMicro test Repeater",
        "node-saldanha": "Saldanha",
        "node-solar": "Test Solar",
        "node-vredenburg": "Vredenburg",
        "node-vredenburg-ne": "Vredenburg NE",
    }
    for stable_id, name in repeaters.items():
        add_repeater(hass, meshcore_entry, stable_id=stable_id, name=name)

    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: list(reversed(repeaters))},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    device_registry = dr.async_get(hass)
    for stable_id, expected_name in expected_names.items():
        device = device_registry.async_get_device(identifiers={(DOMAIN, stable_id)})
        assert device is not None
        assert device.name == expected_name
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, "node-laguna")}).name
        != "ProMicro Repeater"
    )
    assert len(noc_entry.runtime_data.coordinators) == 8
    entries = er.async_entries_for_config_entry(er.async_get(hass), noc_entry.entry_id)
    assert (
        len(
            [
                entry
                for entry in entries
                if entry.entity_id.split(".", 1)[0] in {"sensor", "binary_sensor"}
            ]
        )
        == 37
    )


async def test_duplicate_friendly_names_keep_stable_identity(
    hass: HomeAssistant,
) -> None:
    """Friendly-name collisions cannot merge devices or unique IDs."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="duplicate-a", name="Repeater")
    add_repeater(hass, meshcore_entry, stable_id="duplicate-b", name="Repeater")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={
            CONF_MANAGED_REPEATER_IDS: [
                "duplicate-a",
                "duplicate-b",
                "duplicate-a",
            ]
        },
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    device_registry = dr.async_get(hass)
    devices = [
        device_registry.async_get_device(identifiers={(DOMAIN, stable_id)})
        for stable_id in ("duplicate-a", "duplicate-b")
    ]
    assert all(device is not None for device in devices)
    assert devices[0].id != devices[1].id
    assert len(noc_entry.runtime_data.coordinators) == 2
    entries = er.async_entries_for_config_entry(er.async_get(hass), noc_entry.entry_id)
    unique_ids = [
        entry.unique_id
        for entry in entries
        if entry.entity_id.split(".", 1)[0] in {"sensor", "binary_sensor"}
    ]
    assert len(unique_ids) == 13
    assert len(unique_ids) == len(set(unique_ids))

    diagnostics = await async_get_config_entry_diagnostics(hass, noc_entry)
    assert not diagnostics["duplicate_detection"]["duplicates_detected"]
