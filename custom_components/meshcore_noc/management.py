"""Persistent per-repeater management settings.

Passwords deliberately stay behind this module's private storage boundary.  The
public representation only reports whether a password is configured.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    AGING_MAX_AGE,
    DOMAIN,
    EMPTY_VOLTAGE,
    FRESH_MAX_AGE,
    FULL_VOLTAGE,
    STALE_MAX_AGE,
    VOLTAGE_OFFSET,
)
from .epoch_sync import install_epoch_sync

_STORAGE_VERSION = 1
_PASSWORD = "password"
_PASSWORD_CHANGED_AT = "password_changed_at"

# Install the backend clock workflow before a clock-manager instance starts.
install_epoch_sync()


class ManagementStore(Protocol):
    """Minimal Home Assistant storage contract used by tests."""

    async def async_load(self) -> dict[str, Any] | None:
        """Load stored data."""

    async def async_save(self, data: dict[str, Any]) -> None:
        """Save stored data."""


@dataclass(frozen=True, slots=True)
class RepeaterSettings:
    """Validated non-secret settings for one managed repeater."""

    voltage_offset: float = VOLTAGE_OFFSET
    empty_voltage: float = EMPTY_VOLTAGE
    full_voltage: float = FULL_VOLTAGE
    battery_warning: int = 40
    battery_critical: int = 20
    fresh_max_age: int = FRESH_MAX_AGE
    aging_max_age: int = AGING_MAX_AGE
    stale_max_age: int = STALE_MAX_AGE
    offline_max_age: int = STALE_MAX_AGE
    clock_warning: int = 120
    clock_critical: int = 300
    display_name: str | None = None

    def public_dict(self, *, password_configured: bool) -> dict[str, Any]:
        """Return the browser-safe representation."""
        return {**asdict(self), "password_configured": password_configured}


DEFAULT_REPEATER_SETTINGS = RepeaterSettings()


class RepeaterSettingsValidationError(ValueError):
    """Raised when an operator-supplied value is invalid."""


def validate_repeater_settings(values: Mapping[str, Any]) -> RepeaterSettings:
    """Validate and normalize a complete settings payload."""
    try:
        settings = RepeaterSettings(
            voltage_offset=float(values["voltage_offset"]),
            empty_voltage=float(values["empty_voltage"]),
            full_voltage=float(values["full_voltage"]),
            battery_warning=int(values["battery_warning"]),
            battery_critical=int(values["battery_critical"]),
            fresh_max_age=int(values["fresh_max_age"]),
            aging_max_age=int(values["aging_max_age"]),
            stale_max_age=int(values["stale_max_age"]),
            offline_max_age=int(values["offline_max_age"]),
            clock_warning=int(values["clock_warning"]),
            clock_critical=int(values["clock_critical"]),
            display_name=(str(values.get("display_name") or "").strip()[:80] or None),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise RepeaterSettingsValidationError(
            "All settings must contain valid numeric values"
        ) from err

    if not -2.0 <= settings.voltage_offset <= 2.0:
        raise RepeaterSettingsValidationError(
            "Voltage offset must be between -2.0 V and 2.0 V"
        )
    if not 2.0 <= settings.empty_voltage < settings.full_voltage <= 6.0:
        raise RepeaterSettingsValidationError(
            "Empty voltage must be below full voltage; both must be 2.0–6.0 V"
        )
    if not 0 <= settings.battery_critical < settings.battery_warning <= 100:
        raise RepeaterSettingsValidationError(
            "Battery critical must be below battery warning (0–100%)"
        )
    if not (
        60
        <= settings.fresh_max_age
        < settings.aging_max_age
        < settings.stale_max_age
        <= settings.offline_max_age
        <= 604_800
    ):
        raise RepeaterSettingsValidationError(
            "Fresh, aging, stale and offline ages must increase and be "
            "between 60 seconds and 7 days"
        )
    if not 0 < settings.clock_warning < settings.clock_critical <= 86_400:
        raise RepeaterSettingsValidationError(
            "Clock warning must be below clock critical (maximum 24 hours)"
        )
    return settings


class RepeaterManagementStore:
    """Private persistent settings keyed only by NOC stable ID."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_key: str,
        *,
        store: ManagementStore | None = None,
    ) -> None:
        self._store = store or Store(
            hass,
            _STORAGE_VERSION,
            storage_key,
            private=True,
        )
        self._records: dict[str, dict[str, Any]] = {}

    async def async_initialize(self) -> None:
        """Load settings, ignoring malformed records safely."""
        stored = await self._store.async_load()
        records = stored.get("repeaters", {}) if isinstance(stored, dict) else {}
        if isinstance(records, dict):
            self._records = {
                str(stable_id): dict(record)
                for stable_id, record in records.items()
                if isinstance(record, dict)
            }

    def settings_for(self, stable_id: str) -> RepeaterSettings:
        """Return validated settings or defaults for one stable ID."""
        record = self._records.get(stable_id)
        if not record:
            return DEFAULT_REPEATER_SETTINGS
        public = {
            field: record.get(field, getattr(DEFAULT_REPEATER_SETTINGS, field))
            for field in asdict(DEFAULT_REPEATER_SETTINGS)
        }
        try:
            return validate_repeater_settings(public)
        except RepeaterSettingsValidationError:
            return DEFAULT_REPEATER_SETTINGS

    def password_for(self, stable_id: str) -> str | None:
        """Return a secret only to an authenticated backend caller."""
        value = self._records.get(stable_id, {}).get(_PASSWORD)
        return value if isinstance(value, str) and value else None

    def public_settings(self, stable_id: str) -> dict[str, Any]:
        """Return settings without secret material."""
        record = self._records.get(stable_id, {})
        changed_at = record.get(_PASSWORD_CHANGED_AT)
        return self.settings_for(stable_id).public_dict(
            password_configured=self.password_for(stable_id) is not None
        ) | {
            "password_last_changed": changed_at if isinstance(changed_at, str) else None
        }

    async def async_save_settings(
        self, stable_id: str, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist one complete validated non-secret record."""
        settings = validate_repeater_settings(values)
        existing = self._records.get(stable_id, {})
        self._records[stable_id] = {
            **asdict(settings),
            **({_PASSWORD: existing[_PASSWORD]} if _PASSWORD in existing else {}),
            **(
                {_PASSWORD_CHANGED_AT: existing[_PASSWORD_CHANGED_AT]}
                if _PASSWORD_CHANGED_AT in existing
                else {}
            ),
        }
        await self._async_commit()
        return self.public_settings(stable_id)

    async def async_reset_settings(self, stable_id: str) -> dict[str, Any]:
        """Reset non-secret values while retaining the password."""
        existing_password = self.password_for(stable_id)
        password_changed_at = self._records.get(stable_id, {}).get(_PASSWORD_CHANGED_AT)
        self._records[stable_id] = asdict(DEFAULT_REPEATER_SETTINGS)
        if existing_password is not None:
            self._records[stable_id][_PASSWORD] = existing_password
        if password_changed_at is not None:
            self._records[stable_id][_PASSWORD_CHANGED_AT] = password_changed_at
        await self._async_commit()
        return self.public_settings(stable_id)

    async def async_set_password(self, stable_id: str, password: str) -> None:
        """Replace the password without ever returning it."""
        if not isinstance(password, str) or not password:
            raise RepeaterSettingsValidationError("Enter a new repeater password")
        if len(password) > 256:
            raise RepeaterSettingsValidationError(
                "Repeater password must be 256 characters or fewer"
            )
        record = self._records.setdefault(stable_id, asdict(DEFAULT_REPEATER_SETTINGS))
        record[_PASSWORD] = password
        record[_PASSWORD_CHANGED_AT] = datetime.now(UTC).isoformat()
        await self._async_commit()

    async def async_remove_password(self, stable_id: str) -> None:
        """Remove the stored password for one repeater."""
        record = self._records.get(stable_id)
        if record is not None:
            record.pop(_PASSWORD, None)
            record.pop(_PASSWORD_CHANGED_AT, None)
            await self._async_commit()

    async def _async_commit(self) -> None:
        await self._store.async_save({"repeaters": self._records})


def _runtime_for_stable_id(
    hass: HomeAssistant, stable_id: str
) -> tuple[Any, RepeaterManagementStore]:
    """Resolve an active managed stable ID without accepting friendly names."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            continue
        if any(
            coordinator.source.stable_id == stable_id
            for coordinator in runtime.coordinators
        ):
            return runtime, runtime.management_store
    raise RepeaterSettingsValidationError(
        f"{stable_id!r} is not a currently managed repeater stable ID"
    )


def _send_error(
    connection: websocket_api.ActiveConnection,
    message_id: int,
    err: RepeaterSettingsValidationError,
) -> None:
    connection.send_error(message_id, "invalid_repeater_settings", str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "meshcore_noc/management/get",
        vol.Required("stable_id"): str,
    }
)
@websocket_api.async_response
async def websocket_get_repeater_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return browser-safe settings to an administrator."""
    connection.require_admin()
    try:
        _runtime, manager = _runtime_for_stable_id(hass, msg["stable_id"])
    except RepeaterSettingsValidationError as err:
        _send_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], manager.public_settings(msg["stable_id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "meshcore_noc/management/save",
        vol.Required("stable_id"): str,
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response
async def websocket_save_repeater_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Validate and save browser-safe settings."""
    connection.require_admin()
    try:
        runtime, manager = _runtime_for_stable_id(hass, msg["stable_id"])
        result = await manager.async_save_settings(msg["stable_id"], msg["settings"])
        coordinator = next(
            item
            for item in runtime.coordinators
            if item.source.stable_id == msg["stable_id"]
        )
        await coordinator.async_request_refresh()
    except RepeaterSettingsValidationError as err:
        _send_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "meshcore_noc/management/reset",
        vol.Required("stable_id"): str,
    }
)
@websocket_api.async_response
async def websocket_reset_repeater_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Reset non-secret values to defaults."""
    connection.require_admin()
    try:
        runtime, manager = _runtime_for_stable_id(hass, msg["stable_id"])
        result = await manager.async_reset_settings(msg["stable_id"])
        coordinator = next(
            item
            for item in runtime.coordinators
            if item.source.stable_id == msg["stable_id"]
        )
        await coordinator.async_request_refresh()
    except RepeaterSettingsValidationError as err:
        _send_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "meshcore_noc/management/set_password",
        vol.Required("stable_id"): str,
        vol.Required("password"): str,
    }
)
@websocket_api.async_response
async def websocket_set_repeater_password(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Replace one password without returning or logging it."""
    connection.require_admin()
    try:
        _runtime, manager = _runtime_for_stable_id(hass, msg["stable_id"])
        await manager.async_set_password(msg["stable_id"], msg["password"])
    except RepeaterSettingsValidationError as err:
        _send_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], manager.public_settings(msg["stable_id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "meshcore_noc/management/remove_password",
        vol.Required("stable_id"): str,
    }
)
@websocket_api.async_response
async def websocket_remove_repeater_password(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove one password without exposing its former value."""
    connection.require_admin()
    try:
        _runtime, manager = _runtime_for_stable_id(hass, msg["stable_id"])
        await manager.async_remove_password(msg["stable_id"])
    except RepeaterSettingsValidationError as err:
        _send_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], manager.public_settings(msg["stable_id"]))


def async_register_management_websockets(hass: HomeAssistant) -> None:
    """Register the administrator-only management API once."""
    for command in (
        websocket_get_repeater_settings,
        websocket_save_repeater_settings,
        websocket_reset_repeater_settings,
        websocket_set_repeater_password,
        websocket_remove_repeater_password,
    ):
        websocket_api.async_register_command(hass, command)
