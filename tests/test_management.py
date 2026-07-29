"""Tests for private per-repeater management persistence."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from inspect import unwrap
from secrets import token_urlsafe
from types import SimpleNamespace

import pytest

from custom_components.meshcore_noc.management import (
    DEFAULT_REPEATER_SETTINGS,
    RepeaterManagementStore,
    RepeaterSettingsValidationError,
    validate_repeater_settings,
    websocket_get_repeater_settings,
    websocket_set_repeater_password,
)


class _Store:
    def __init__(self, data=None) -> None:
        self.data = deepcopy(data)
        self.saves = 0

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        self.data = deepcopy(data)
        self.saves += 1


def _values(**changes):
    values = DEFAULT_REPEATER_SETTINGS.public_dict(password_configured=False)
    values.pop("password_configured")
    values.update(changes)
    return values


def _password() -> str:
    """Create an ephemeral value that can never be checked into the repository."""
    return token_urlsafe(24)


def test_management_validation_rejects_invalid_ranges() -> None:
    """Calibration, health and time thresholds are validated together."""
    with pytest.raises(RepeaterSettingsValidationError, match="Empty voltage"):
        validate_repeater_settings(_values(empty_voltage=4.3, full_voltage=4.2))
    with pytest.raises(RepeaterSettingsValidationError, match="Battery critical"):
        validate_repeater_settings(_values(battery_critical=50, battery_warning=40))
    with pytest.raises(RepeaterSettingsValidationError, match="must increase"):
        validate_repeater_settings(_values(fresh_max_age=8000))
    with pytest.raises(RepeaterSettingsValidationError, match="Clock warning"):
        validate_repeater_settings(_values(clock_warning=500, clock_critical=300))


@pytest.mark.asyncio
async def test_settings_and_password_persist_per_stable_id(monkeypatch) -> None:
    """Reload restores settings and a secret never enters public output."""
    moments = iter(
        (
            datetime(2026, 7, 29, 10, 0, tzinfo=UTC),
            datetime(2026, 7, 29, 10, 1, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.management.datetime",
        SimpleNamespace(now=lambda _timezone: next(moments)),
    )
    store = _Store()
    manager = RepeaterManagementStore(None, "test", store=store)
    await manager.async_initialize()
    saved = await manager.async_save_settings(
        "laguna-stable",
        _values(
            voltage_offset=-0.5,
            display_name="Laguna Operations",
            clock_warning=90,
        ),
    )
    password = _password()
    await manager.async_set_password("laguna-stable", password)
    changed_at = manager.public_settings("laguna-stable")["password_last_changed"]

    assert saved["voltage_offset"] == -0.5
    assert "password" not in manager.public_settings("laguna-stable")
    assert manager.public_settings("laguna-stable")["password_configured"]
    assert changed_at is not None

    replacement_password = _password()
    await manager.async_set_password("laguna-stable", replacement_password)
    replaced_at = manager.public_settings("laguna-stable")["password_last_changed"]
    assert replaced_at is not None
    assert replaced_at != changed_at

    restored = RepeaterManagementStore(None, "test", store=store)
    await restored.async_initialize()
    assert restored.settings_for("laguna-stable").display_name == "Laguna Operations"
    assert restored.settings_for("laguna-stable").clock_warning == 90
    assert restored.password_for("laguna-stable") == replacement_password
    assert (
        restored.public_settings("laguna-stable")["password_last_changed"]
        == replaced_at
    )
    assert restored.settings_for("another") == DEFAULT_REPEATER_SETTINGS


@pytest.mark.asyncio
async def test_reset_retains_password_and_remove_clears_only_secret() -> None:
    """Non-secret reset and password removal are intentionally independent."""
    store = _Store()
    manager = RepeaterManagementStore(None, "test", store=store)
    await manager.async_initialize()
    await manager.async_save_settings(
        "managed-id", _values(voltage_offset=0.25, display_name="Custom")
    )
    await manager.async_set_password("managed-id", _password())

    reset = await manager.async_reset_settings("managed-id")
    assert reset["voltage_offset"] == DEFAULT_REPEATER_SETTINGS.voltage_offset
    assert reset["display_name"] is None
    assert reset["password_configured"]

    await manager.async_remove_password("managed-id")
    assert manager.password_for("managed-id") is None
    assert not manager.public_settings("managed-id")["password_configured"]
    assert manager.public_settings("managed-id")["password_last_changed"] is None


@pytest.mark.asyncio
async def test_repeater_records_are_isolated_by_stable_id() -> None:
    """Saving one repeater cannot mutate another repeater's record."""
    manager = RepeaterManagementStore(None, "test", store=_Store())
    await manager.async_initialize()
    await manager.async_save_settings(
        "first-stable", _values(display_name="First", voltage_offset=-0.25)
    )
    await manager.async_save_settings(
        "second-stable", _values(display_name="Second", voltage_offset=0.25)
    )

    assert manager.settings_for("first-stable").display_name == "First"
    assert manager.settings_for("first-stable").voltage_offset == -0.25
    assert manager.settings_for("second-stable").display_name == "Second"
    assert manager.settings_for("second-stable").voltage_offset == 0.25


class _Connection:
    def __init__(self, *, admin: bool) -> None:
        self.admin = admin
        self.results = []
        self.errors = []

    def require_admin(self) -> None:
        if not self.admin:
            raise PermissionError("administrator required")

    def send_result(self, message_id, result) -> None:
        self.results.append((message_id, result))

    def send_error(self, message_id, code, message) -> None:
        self.errors.append((message_id, code, message))


class _ConfigEntries:
    def __init__(self, runtime) -> None:
        self.runtime = runtime

    def async_entries(self, _domain):
        return [SimpleNamespace(runtime_data=self.runtime)]


@pytest.mark.asyncio
async def test_password_websocket_is_admin_only_and_never_echoes_value() -> None:
    """Only admins can replace a password and the response is boolean-only."""
    manager = RepeaterManagementStore(None, "test", store=_Store())
    await manager.async_initialize()
    runtime = SimpleNamespace(
        management_store=manager,
        coordinators=[
            SimpleNamespace(source=SimpleNamespace(stable_id="managed-stable"))
        ],
    )
    hass = SimpleNamespace(config_entries=_ConfigEntries(runtime))
    password = _password()

    denied = _Connection(admin=False)
    with pytest.raises(PermissionError, match="administrator"):
        await unwrap(websocket_set_repeater_password)(
            hass,
            denied,
            {
                "id": 1,
                "type": "meshcore_noc/management/set_password",
                "stable_id": "managed-stable",
                "password": password,
            },
        )

    allowed = _Connection(admin=True)
    await unwrap(websocket_set_repeater_password)(
        hass,
        allowed,
        {
            "id": 2,
            "type": "meshcore_noc/management/set_password",
            "stable_id": "managed-stable",
            "password": password,
        },
    )
    await unwrap(websocket_get_repeater_settings)(
        hass,
        allowed,
        {
            "id": 3,
            "type": "meshcore_noc/management/get",
            "stable_id": "managed-stable",
        },
    )

    assert allowed.results[0][0] == 2
    assert allowed.results[0][1]["password_configured"] is True
    assert allowed.results[0][1]["password_last_changed"] is not None
    assert allowed.results[1][1]["password_configured"] is True
    assert password not in repr(allowed.results)
