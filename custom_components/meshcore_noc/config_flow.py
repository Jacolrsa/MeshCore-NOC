"""Config and options flows for MeshCore NOC."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_AUTO_FLEET_CLOCK_CHECKS,
    CONF_CLOCK_CHECK_COOLDOWN,
    CONF_FLEET_CLOCK_INTERVAL_HOURS,
    CONF_FLEET_FAILURE_DELAY,
    CONF_FLEET_ROTATING_START,
    CONF_FLEET_SUCCESS_DELAY,
    CONF_MANAGED_REPEATER_IDS,
    CONF_MESHCORE_CONFIG_ENTRY_IDS,
    CONF_UPDATE_CHANNEL,
    DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    DEFAULT_CLOCK_CHECK_COOLDOWN,
    DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    DEFAULT_FLEET_FAILURE_DELAY,
    DEFAULT_FLEET_ROTATING_START,
    DEFAULT_FLEET_SUCCESS_DELAY,
    DEFAULT_UPDATE_CHANNEL,
    DOMAIN,
    INTEGRATION_NAME,
    MAX_CLOCK_CHECK_COOLDOWN,
    MAX_FLEET_CLOCK_INTERVAL_HOURS,
    MAX_FLEET_FAILURE_DELAY,
    MAX_FLEET_SUCCESS_DELAY,
    MESHCORE_DOMAIN,
    MIN_CLOCK_CHECK_COOLDOWN,
    MIN_FLEET_CLOCK_INTERVAL_HOURS,
    MIN_FLEET_FAILURE_DELAY,
    MIN_FLEET_SUCCESS_DELAY,
    UPDATE_CHANNEL_DEVELOPMENT,
    UPDATE_CHANNEL_STABLE,
)
from .discovery import async_discover_repeaters
from .models import DeviceType, DiscoveredSourceRepeater

_DEVICE_LABELS = {
    DeviceType.REPEATER: ("📡", 0),
    DeviceType.CLIENT: ("📱", 1),
    DeviceType.UNKNOWN: ("❔", 2),
}

_MESHCORE_PREFIX = re.compile(
    r"^\s*meshcore(?:\s+(?:repeater|client))?\s*:?\s*",
    re.IGNORECASE,
)
_TRAILING_SHORT_ID = re.compile(r"\s*\([0-9a-f]{6}\)\s*$", re.IGNORECASE)
_UPDATE_CHANNELS = {UPDATE_CHANNEL_STABLE, UPDATE_CHANNEL_DEVELOPMENT}


def _ui_display_name(display_name: str, stable_id: str) -> str:
    """Normalize a device name for selector presentation only."""
    normalized = _MESHCORE_PREFIX.sub("", display_name, count=1)
    normalized = _TRAILING_SHORT_ID.sub("", normalized, count=1)
    normalized = " ".join(normalized.split())
    return normalized or display_name.strip() or stable_id


def _device_label(device: DiscoveredSourceRepeater) -> str:
    """Return a concise UI label without changing stored device metadata."""
    icon, _ = _DEVICE_LABELS[device.device_type]
    return f"{icon} {_ui_display_name(device.display_name, device.stable_id)}"


def _selection_options(
    devices: Mapping[str, DiscoveredSourceRepeater],
) -> list[dict[str, str]]:
    """Build selector options with stable values and UI-only labels."""
    return [
        {"value": stable_id, "label": _device_label(device)}
        for stable_id, device in sorted(
            devices.items(),
            key=lambda item: (
                _DEVICE_LABELS[item[1].device_type][1],
                item[1].display_name.casefold(),
            ),
        )
    ]


def _selection_schema(
    repeaters: Mapping[str, DiscoveredSourceRepeater],
    selected: list[str] | tuple[str, ...],
    update_channel: str = DEFAULT_UPDATE_CHANNEL,
    clock_check_cooldown: int = DEFAULT_CLOCK_CHECK_COOLDOWN,
    auto_fleet_clock_checks: bool = DEFAULT_AUTO_FLEET_CLOCK_CHECKS,
    fleet_clock_interval_hours: int = DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
    fleet_success_delay: int = DEFAULT_FLEET_SUCCESS_DELAY,
    fleet_failure_delay: int = DEFAULT_FLEET_FAILURE_DELAY,
    fleet_rotating_start: bool = DEFAULT_FLEET_ROTATING_START,
) -> vol.Schema:
    """Build a stable-ID multi-select with type-prefixed display labels."""
    options = _selection_options(repeaters)
    available_ids = set(repeaters)
    default = [stable_id for stable_id in selected if stable_id in available_ids]
    return vol.Schema(
        {
            vol.Required(CONF_MANAGED_REPEATER_IDS, default=default): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True)
            ),
            vol.Required(CONF_UPDATE_CHANNEL, default=update_channel): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": UPDATE_CHANNEL_STABLE, "label": "Stable"},
                        {
                            "value": UPDATE_CHANNEL_DEVELOPMENT,
                            "label": "Development",
                        },
                    ],
                    multiple=False,
                )
            ),
            vol.Required(
                CONF_CLOCK_CHECK_COOLDOWN, default=clock_check_cooldown
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_CLOCK_CHECK_COOLDOWN,
                    max=MAX_CLOCK_CHECK_COOLDOWN,
                    step=30,
                    unit_of_measurement="seconds",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_AUTO_FLEET_CLOCK_CHECKS, default=auto_fleet_clock_checks
            ): BooleanSelector(),
            vol.Required(
                CONF_FLEET_CLOCK_INTERVAL_HOURS,
                default=fleet_clock_interval_hours,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_FLEET_CLOCK_INTERVAL_HOURS,
                    max=MAX_FLEET_CLOCK_INTERVAL_HOURS,
                    step=1,
                    unit_of_measurement="hours",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FLEET_SUCCESS_DELAY, default=fleet_success_delay
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_FLEET_SUCCESS_DELAY,
                    max=MAX_FLEET_SUCCESS_DELAY,
                    step=1,
                    unit_of_measurement="seconds",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FLEET_FAILURE_DELAY, default=fleet_failure_delay
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_FLEET_FAILURE_DELAY,
                    max=MAX_FLEET_FAILURE_DELAY,
                    step=1,
                    unit_of_measurement="seconds",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FLEET_ROTATING_START, default=fleet_rotating_start
            ): BooleanSelector(),
        }
    )


def _fleet_options(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize fleet options from flow input."""
    return {
        CONF_AUTO_FLEET_CLOCK_CHECKS: bool(
            user_input.get(
                CONF_AUTO_FLEET_CLOCK_CHECKS, DEFAULT_AUTO_FLEET_CLOCK_CHECKS
            )
        ),
        CONF_FLEET_CLOCK_INTERVAL_HOURS: int(
            user_input.get(
                CONF_FLEET_CLOCK_INTERVAL_HOURS,
                DEFAULT_FLEET_CLOCK_INTERVAL_HOURS,
            )
        ),
        CONF_FLEET_SUCCESS_DELAY: int(
            user_input.get(CONF_FLEET_SUCCESS_DELAY, DEFAULT_FLEET_SUCCESS_DELAY)
        ),
        CONF_FLEET_FAILURE_DELAY: int(
            user_input.get(CONF_FLEET_FAILURE_DELAY, DEFAULT_FLEET_FAILURE_DELAY)
        ),
        CONF_FLEET_ROTATING_START: bool(
            user_input.get(CONF_FLEET_ROTATING_START, DEFAULT_FLEET_ROTATING_START)
        ),
    }


def _valid_fleet_options(options: Mapping[str, Any]) -> bool:
    """Validate all bounded fleet timing options."""
    return (
        MIN_FLEET_CLOCK_INTERVAL_HOURS
        <= options[CONF_FLEET_CLOCK_INTERVAL_HOURS]
        <= MAX_FLEET_CLOCK_INTERVAL_HOURS
        and MIN_FLEET_SUCCESS_DELAY
        <= options[CONF_FLEET_SUCCESS_DELAY]
        <= MAX_FLEET_SUCCESS_DELAY
        and MIN_FLEET_FAILURE_DELAY
        <= options[CONF_FLEET_FAILURE_DELAY]
        <= MAX_FLEET_FAILURE_DELAY
    )


class MeshCoreNocConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the single MeshCore NOC instance."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Discover MeshCore devices and select those managed by NOC."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        meshcore_entries = self.hass.config_entries.async_entries(MESHCORE_DOMAIN)
        if not meshcore_entries:
            return self.async_abort(reason="meshcore_not_installed")

        discovery = await async_discover_repeaters(self.hass)
        if user_input is not None:
            selected = list(user_input[CONF_MANAGED_REPEATER_IDS])
            update_channel = user_input.get(CONF_UPDATE_CHANNEL, DEFAULT_UPDATE_CHANNEL)
            clock_check_cooldown = int(
                user_input.get(CONF_CLOCK_CHECK_COOLDOWN, DEFAULT_CLOCK_CHECK_COOLDOWN)
            )
            fleet_options = _fleet_options(user_input)
            valid_ids = set(discovery.repeaters)
            invalid_selection = any(
                stable_id not in valid_ids for stable_id in selected
            )
            invalid_cooldown = not (
                MIN_CLOCK_CHECK_COOLDOWN
                <= clock_check_cooldown
                <= MAX_CLOCK_CHECK_COOLDOWN
            )
            if (
                invalid_selection
                or update_channel not in _UPDATE_CHANNELS
                or invalid_cooldown
                or not _valid_fleet_options(fleet_options)
            ):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_selection_schema(
                        discovery.repeaters,
                        selected,
                        update_channel,
                        clock_check_cooldown,
                        **fleet_options,
                    ),
                    errors={
                        "base": (
                            "invalid_repeater_selection"
                            if invalid_selection
                            else (
                                "invalid_update_channel"
                                if update_channel not in _UPDATE_CHANNELS
                                else (
                                    "invalid_clock_check_cooldown"
                                    if invalid_cooldown
                                    else "invalid_fleet_clock_options"
                                )
                            )
                        )
                    },
                )
            return self.async_create_entry(
                title=INTEGRATION_NAME,
                data={
                    CONF_MESHCORE_CONFIG_ENTRY_IDS: list(
                        discovery.meshcore_config_entry_ids
                    )
                },
                options={
                    CONF_MANAGED_REPEATER_IDS: selected,
                    CONF_UPDATE_CHANNEL: update_channel,
                    CONF_CLOCK_CHECK_COOLDOWN: clock_check_cooldown,
                    **fleet_options,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_selection_schema(discovery.repeaters, []),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MeshCoreNocOptionsFlow:
        """Return the managed-repeater options flow."""
        return MeshCoreNocOptionsFlow()


class MeshCoreNocOptionsFlow(config_entries.OptionsFlow):
    """Change the repeaters managed by MeshCore NOC."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show available and currently managed repeaters in one multi-select."""
        discovery = await async_discover_repeaters(self.hass)
        current = list(self.config_entry.options.get(CONF_MANAGED_REPEATER_IDS, []))
        current_channel = self.config_entry.options.get(
            CONF_UPDATE_CHANNEL, DEFAULT_UPDATE_CHANNEL
        )
        current_clock_check_cooldown = int(
            self.config_entry.options.get(
                CONF_CLOCK_CHECK_COOLDOWN, DEFAULT_CLOCK_CHECK_COOLDOWN
            )
        )
        current_fleet_options = _fleet_options(self.config_entry.options)
        if user_input is not None:
            selected = list(user_input[CONF_MANAGED_REPEATER_IDS])
            update_channel = user_input.get(CONF_UPDATE_CHANNEL, current_channel)
            clock_check_cooldown = int(
                user_input.get(CONF_CLOCK_CHECK_COOLDOWN, current_clock_check_cooldown)
            )
            fleet_options = {
                key: value
                for key, value in _fleet_options(
                    {**current_fleet_options, **user_input}
                ).items()
            }
            valid_ids = set(discovery.repeaters)
            invalid_selection = any(
                stable_id not in valid_ids for stable_id in selected
            )
            invalid_cooldown = not (
                MIN_CLOCK_CHECK_COOLDOWN
                <= clock_check_cooldown
                <= MAX_CLOCK_CHECK_COOLDOWN
            )
            if (
                invalid_selection
                or update_channel not in _UPDATE_CHANNELS
                or invalid_cooldown
                or not _valid_fleet_options(fleet_options)
            ):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_selection_schema(
                        discovery.repeaters,
                        selected,
                        update_channel,
                        clock_check_cooldown,
                        **fleet_options,
                    ),
                    errors={
                        "base": (
                            "invalid_repeater_selection"
                            if invalid_selection
                            else (
                                "invalid_update_channel"
                                if update_channel not in _UPDATE_CHANNELS
                                else (
                                    "invalid_clock_check_cooldown"
                                    if invalid_cooldown
                                    else "invalid_fleet_clock_options"
                                )
                            )
                        )
                    },
                )
            return self.async_create_entry(
                title="",
                data={
                    CONF_MANAGED_REPEATER_IDS: selected,
                    CONF_UPDATE_CHANNEL: update_channel,
                    CONF_CLOCK_CHECK_COOLDOWN: clock_check_cooldown,
                    **fleet_options,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_selection_schema(
                discovery.repeaters,
                current,
                current_channel,
                current_clock_check_cooldown,
                **current_fleet_options,
            ),
        )
