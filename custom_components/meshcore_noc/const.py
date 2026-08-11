"""Constants for MeshCore NOC."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "meshcore_noc"
MESHCORE_DOMAIN: Final = "meshcore"
MESHCORE_RAW_EVENT: Final = "meshcore_raw_event"
INTEGRATION_NAME: Final = "MeshCore NOC"
INTEGRATION_VERSION: Final = "1.1.0-beta12"

PLATFORMS: Final = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.UPDATE,
)

ALPHA2_DEVICE_NAME: Final = "📡 ProMicro Repeater"
ALPHA2_DEVICE_SLUG: Final = "promicro_repeater"

VOLTAGE_OFFSET: Final = -0.816
EMPTY_VOLTAGE: Final = 3.000
FULL_VOLTAGE: Final = 4.200
MIN_VALID_VOLTAGE: Final = 2.500
MAX_VALID_VOLTAGE: Final = 5.000

FRESH_MAX_AGE: Final = 4_500
AGING_MAX_AGE: Final = 7_200
STALE_MAX_AGE: Final = 10_800

CONF_MANAGED_REPEATER_IDS: Final = "managed_repeater_ids"
CONF_MESHCORE_CONFIG_ENTRY_IDS: Final = "meshcore_config_entry_ids"
CONF_CLOCK_CHECK_COOLDOWN: Final = "clock_check_cooldown"
CONF_AUTO_FLEET_CLOCK_CHECKS: Final = "auto_fleet_clock_checks"
CONF_FLEET_CLOCK_INTERVAL_HOURS: Final = "fleet_clock_interval_hours"
CONF_FLEET_SUCCESS_DELAY: Final = "fleet_success_delay"
CONF_FLEET_FAILURE_DELAY: Final = "fleet_failure_delay"
CONF_FLEET_ROTATING_START: Final = "fleet_rotating_start"
CONF_AUTO_FLEET_CLOCK_SYNC: Final = "auto_fleet_clock_sync"
CONF_FLEET_CLOCK_SYNC_INTERVAL_HOURS: Final = "fleet_clock_sync_interval_hours"
CONF_UPDATE_CHANNEL: Final = "update_channel"
DEFAULT_CLOCK_CHECK_COOLDOWN: Final = 300
MIN_CLOCK_CHECK_COOLDOWN: Final = 60
MAX_CLOCK_CHECK_COOLDOWN: Final = 3_600
CLOCK_RESPONSE_TIMEOUT: Final = 30
CLOCK_HISTORY_LIMIT: Final = 20
FLEET_CLOCK_HISTORY_LIMIT: Final = 20
DEFAULT_AUTO_FLEET_CLOCK_CHECKS: Final = False
DEFAULT_FLEET_CLOCK_INTERVAL_HOURS: Final = 6
MIN_FLEET_CLOCK_INTERVAL_HOURS: Final = 1
MAX_FLEET_CLOCK_INTERVAL_HOURS: Final = 168
DEFAULT_FLEET_SUCCESS_DELAY: Final = 15
MIN_FLEET_SUCCESS_DELAY: Final = 0
MAX_FLEET_SUCCESS_DELAY: Final = 300
DEFAULT_FLEET_FAILURE_DELAY: Final = 30
MIN_FLEET_FAILURE_DELAY: Final = 0
MAX_FLEET_FAILURE_DELAY: Final = 600
DEFAULT_FLEET_ROTATING_START: Final = False
DEFAULT_AUTO_FLEET_CLOCK_SYNC: Final = False
DEFAULT_FLEET_CLOCK_SYNC_INTERVAL_HOURS: Final = 24
FLEET_CLOCK_SYNC_INTERVAL_OPTIONS: Final = (6, 12, 24, 72, 168)
DEFAULT_FLEET_CLOCK_SYNC_DELAY: Final = 2
SERVICE_CHECK_CLOCK: Final = "check_clock"
SERVICE_SYNC_REPEATER_CLOCK: Final = "sync_repeater_clock"
SERVICE_SYNC_ALL_REPEATER_CLOCKS: Final = "sync_all_repeater_clocks"
SERVICE_CHECK_ALL_CLOCKS: Final = "check_all_clocks"
SERVICE_CANCEL_CLOCK_CHECK: Final = "cancel_clock_check"
UPDATE_CHANNEL_STABLE: Final = "stable"
UPDATE_CHANNEL_DEVELOPMENT: Final = "development"
DEFAULT_UPDATE_CHANNEL: Final = UPDATE_CHANNEL_STABLE

EXPECTED_SOURCE_ROLES: Final = (
    "voltage",
    "battery_percentage",
    "airtime_utilisation",
    "availability",
)
