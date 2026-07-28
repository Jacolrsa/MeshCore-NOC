"""Typed internal models for MeshCore NOC discovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class DeviceType(StrEnum):
    """MeshCore device classifications used for presentation."""

    REPEATER = "repeater"
    CLIENT = "client"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceEntityMappings:
    """MeshCore-owned source entity IDs grouped by their NOC role."""

    voltage: str | None = None
    battery_percentage: str | None = None
    airtime_utilisation: str | None = None
    availability: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return role-to-entity mapping."""
        return {
            "voltage": self.voltage,
            "battery_percentage": self.battery_percentage,
            "airtime_utilisation": self.airtime_utilisation,
            "availability": self.availability,
        }


@dataclass(frozen=True, slots=True)
class MissingSourceInformation:
    """Expected source roles that were not discoverable."""

    roles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandAddressResolution:
    """Evidence used to resolve one MeshCore command address."""

    public_key: str | None = None
    pubkey_prefix: str | None = None
    resolution_source: str | None = None
    resolution_sources_checked: tuple[str, ...] = ()
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredSourceRepeater:
    """A MeshCore device and its source registry relationships.

    The class name remains unchanged for alpha1 API compatibility. Its records
    may represent repeaters, clients, or devices whose type is not yet known.
    """

    stable_id: str
    display_name: str
    device_registry_id: str
    meshcore_config_entry_id: str
    entities: SourceEntityMappings
    missing: MissingSourceInformation
    warnings: tuple[str, ...] = ()
    device_type: DeviceType = DeviceType.UNKNOWN
    device_type_method: str = "unknown"
    confidence_score: int = 0
    mapping_method: str = "registry_ownership"
    source_entity_count: int = 0
    public_key: str | None = None
    pubkey_prefix: str | None = None
    command_address: CommandAddressResolution = field(
        default_factory=CommandAddressResolution
    )


@dataclass(frozen=True, slots=True)
class ManagedRepeaterSelection:
    """The stable IDs selected for NOC monitoring."""

    stable_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Complete registry discovery snapshot."""

    repeaters: Mapping[str, DiscoveredSourceRepeater] = field(
        default_factory=lambda: MappingProxyType({})
    )
    meshcore_config_entry_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        repeaters: dict[str, DiscoveredSourceRepeater],
        meshcore_config_entry_ids: tuple[str, ...],
        warnings: tuple[str, ...] = (),
    ) -> DiscoveryResult:
        """Create an immutable discovery result."""
        return cls(
            repeaters=MappingProxyType(dict(repeaters)),
            meshcore_config_entry_ids=meshcore_config_entry_ids,
            warnings=warnings,
        )


@dataclass(frozen=True, slots=True)
class ManagedDeviceData:
    """One calculated telemetry snapshot for a managed MeshCore device."""

    stable_id: str
    managed_device: str
    source_entity: str | None
    raw_voltage: float | None
    calibrated_voltage: float | None
    battery_percentage: int | None
    calibration_offset: float
    empty_voltage: float
    full_voltage: float
    last_source_update: datetime | None
    age_seconds: int | None
    freshness: str
    health: str
    source_available: bool
