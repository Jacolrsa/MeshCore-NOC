"""Registry-based discovery for MeshCore devices.

MeshCore's registry schema is not defined by this repository. Identity therefore
comes from MeshCore-owned device identifiers. Entity names are used only as a
defensive fallback for assigning optional telemetry roles, never as identity.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import EXPECTED_SOURCE_ROLES, MESHCORE_DOMAIN
from .models import (
    CommandAddressResolution,
    DeviceType,
    DiscoveredSourceRepeater,
    DiscoveryResult,
    MissingSourceInformation,
    SourceEntityMappings,
)

_LOGGER = logging.getLogger(__name__)

_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "voltage": ("voltage", "battery_voltage", "bat_voltage", "bat"),
    "battery_percentage": (
        "battery_percentage",
        "battery_percent",
        "battery_level",
        "battery",
    ),
    "airtime_utilisation": (
        "airtime",
        "airtime_utilisation",
        "airtime_utilization",
        "channel_utilisation",
        "channel_utilization",
    ),
    "availability": (
        "availability",
        "available",
        "last_seen",
        "last_update",
        "online",
        "status",
    ),
}

_DEVICE_TYPE_TOKENS: dict[DeviceType, tuple[str, ...]] = {
    DeviceType.REPEATER: ("repeater", "relay"),
    DeviceType.CLIENT: ("client", "companion", "handset"),
}
_PUBLIC_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_PUBKEY_PREFIX_PATTERN = re.compile(r"^[0-9a-fA-F]{12}$")
_HEX_TOKEN_PATTERN = re.compile(
    r"(?<![0-9a-fA-F])([0-9a-fA-F]{12}|[0-9a-fA-F]{64})(?![0-9a-fA-F])"
)


@dataclass(frozen=True, slots=True)
class _RoleCandidate:
    """One ranked entity-to-role mapping."""

    entity_id: str
    role: str
    score: int
    method: str


def _normalize(value: str | None) -> str:
    """Normalize registry metadata for exact token comparisons."""
    return re.sub(r"[^a-z0-9]+", "_", (value or "").casefold()).strip("_")


def _matches_alias(value: str | None, aliases: tuple[str, ...]) -> bool:
    """Return whether normalized metadata is or ends in an exact role alias."""
    normalized = _normalize(value)
    return any(
        normalized == alias or normalized.endswith(f"_{alias}") for alias in aliases
    )


def _contained_alias(value: str | None, aliases: tuple[str, ...]) -> str | None:
    """Return the most specific token-boundary alias found in metadata."""
    padded = f"_{_normalize(value)}_"
    matches = [alias for alias in aliases if f"_{alias}_" in padded]
    return max(matches, key=len) if matches else None


def stable_identifier_from(identifiers: Iterable[tuple[str, str]]) -> str | None:
    """Return a deterministic MeshCore-owned device identifier."""
    candidates = sorted(
        identifier
        for domain, identifier in identifiers
        if domain == MESHCORE_DOMAIN and identifier
    )
    return candidates[0] if candidates else None


def classify_source_role(
    *,
    entity_id: str,
    unique_id: str,
    original_name: str | None,
    translation_key: str | None,
    device_class: str | None,
    unit_of_measurement: str | None,
) -> str | None:
    """Return the strongest optional role classification for compatibility.

    The full discovery path uses the scored candidate function below. This
    wrapper keeps the alpha1 unit-testable boundary intact.
    """
    candidate = _source_role_candidate(
        entity_id=entity_id,
        unique_id=unique_id,
        original_name=original_name,
        translation_key=translation_key,
        device_class=device_class,
        unit_of_measurement=unit_of_measurement,
        disabled=False,
    )
    return candidate.role if candidate else None


def _source_role_candidate(
    *,
    entity_id: str,
    unique_id: str,
    original_name: str | None,
    translation_key: str | None,
    device_class: str | None,
    unit_of_measurement: str | None,
    disabled: bool,
) -> _RoleCandidate | None:
    """Rank one MeshCore-owned entity's strongest source role."""
    normalized_class = (device_class or "").casefold()
    normalized_unit = (unit_of_measurement or "").casefold()
    candidates: list[_RoleCandidate] = []
    penalty = 10 if disabled else 0

    if normalized_class == "voltage":
        candidates.append(
            _RoleCandidate(entity_id, "voltage", 100 - penalty, "device_class")
        )
    if normalized_class == "battery":
        candidates.append(
            _RoleCandidate(
                entity_id, "battery_percentage", 100 - penalty, "device_class"
            )
        )

    for role, aliases in _ROLE_ALIASES.items():
        if _matches_alias(translation_key, aliases):
            candidates.append(
                _RoleCandidate(entity_id, role, 120 - penalty, "translation_key")
            )
        if _matches_alias(unique_id, aliases):
            candidates.append(
                _RoleCandidate(entity_id, role, 115 - penalty, "unique_id")
            )
        if _matches_alias(original_name, aliases):
            candidates.append(
                _RoleCandidate(entity_id, role, 85 - penalty, "original_name")
            )
        if alias := _contained_alias(unique_id, aliases):
            candidates.append(
                _RoleCandidate(
                    entity_id,
                    role,
                    75 + min(15, len(alias) // 2) - penalty,
                    "unique_id_token_fallback",
                )
            )

    if normalized_unit in {"v", "volt", "volts"}:
        candidates.append(_RoleCandidate(entity_id, "voltage", 92 - penalty, "unit"))
    if normalized_unit in {"%", "percent"} and any(
        token in _normalize(unique_id) for token in ("battery", "bat", "battery_level")
    ):
        candidates.append(
            _RoleCandidate(
                entity_id, "battery_percentage", 90 - penalty, "unit_and_unique_id"
            )
        )

    for role, aliases in _ROLE_ALIASES.items():
        if _contained_alias(entity_id, aliases):
            candidates.append(
                _RoleCandidate(entity_id, role, 60 - penalty, "entity_id_fallback")
            )

    return (
        max(candidates, key=lambda item: (item.score, item.role))
        if candidates
        else None
    )


def _contains_device_type(
    values: Iterable[str | None], device_type: DeviceType
) -> bool:
    """Check for an exact device-type token in registry metadata."""
    tokens = {part for value in values for part in _normalize(value).split("_") if part}
    return bool(tokens & set(_DEVICE_TYPE_TOKENS[device_type]))


def _classify_device_type(
    device: dr.DeviceEntry, entities: list[er.RegistryEntry]
) -> tuple[DeviceType, int, str]:
    """Classify a device using structured registry metadata before names."""
    structured_values: list[str | None] = [
        device.model,
        getattr(device, "model_id", None),
        device.manufacturer,
    ]
    structured_matches = {
        device_type
        for device_type in (DeviceType.REPEATER, DeviceType.CLIENT)
        if _contains_device_type(structured_values, device_type)
    }
    if len(structured_matches) == 1:
        return structured_matches.pop(), 95, "device_registry_metadata"
    if len(structured_matches) > 1:
        return DeviceType.UNKNOWN, 20, "conflicting_device_registry_metadata"

    identifier_values = [identifier for _, identifier in device.identifiers]
    identifier_matches = {
        device_type
        for device_type in (DeviceType.REPEATER, DeviceType.CLIENT)
        if _contains_device_type(identifier_values, device_type)
    }
    if len(identifier_matches) == 1:
        return identifier_matches.pop(), 85, "device_identifier_metadata"
    if len(identifier_matches) > 1:
        return DeviceType.UNKNOWN, 20, "conflicting_device_identifier_metadata"

    entity_values = [
        value
        for entity in entities
        for value in (entity.unique_id, entity.translation_key)
    ]
    entity_matches = {
        device_type
        for device_type in (DeviceType.REPEATER, DeviceType.CLIENT)
        if _contains_device_type(entity_values, device_type)
    }
    if len(entity_matches) == 1:
        return entity_matches.pop(), 80, "entity_registry_metadata"
    if len(entity_matches) > 1:
        return DeviceType.UNKNOWN, 20, "conflicting_entity_registry_metadata"

    # Names are mutable metadata and therefore the final, low-confidence fallback.
    name_values = (device.name_by_user, device.name)
    name_matches = {
        device_type
        for device_type in (DeviceType.REPEATER, DeviceType.CLIENT)
        if _contains_device_type(name_values, device_type)
    }
    if len(name_matches) == 1:
        return name_matches.pop(), 55, "display_name_fallback"
    return DeviceType.UNKNOWN, 0, "unclassified"


def _mapping_summary(candidates: Iterable[_RoleCandidate]) -> tuple[int, str]:
    """Summarize role mapping confidence and method for diagnostics."""
    selected = tuple(candidates)
    if not selected:
        return 70, "registry_ownership"
    confidence = min(
        100, round(sum(candidate.score for candidate in selected) / len(selected))
    )
    if any(
        candidate.method in {"entity_id_fallback", "unique_id_token_fallback"}
        for candidate in selected
    ):
        return confidence, "registry_ownership_with_name_fallback"
    return confidence, "registry_ownership_and_exact_metadata"


def _device_name(device: dr.DeviceEntry, stable_id: str) -> str:
    """Return changeable display metadata without using it as identity."""
    return device.name_by_user or device.name or device.model or stable_id


def _entity_metadata(
    hass: HomeAssistant, entity: er.RegistryEntry
) -> tuple[str | None, str | None]:
    """Return device class and unit from registry/state metadata."""
    state = hass.states.get(entity.entity_id)
    attributes: dict[str, Any] = dict(state.attributes) if state else {}
    device_class = getattr(entity, "original_device_class", None) or attributes.get(
        "device_class"
    )
    unit = getattr(entity, "unit_of_measurement", None) or attributes.get(
        "unit_of_measurement"
    )
    return device_class, unit


def _valid_prefix(value: Any) -> str | None:
    """Return one normalized exact MeshCore command prefix."""
    text = str(value or "").strip()
    return text.lower() if _PUBKEY_PREFIX_PATTERN.fullmatch(text) else None


def _valid_public_key(value: Any) -> str | None:
    """Return one normalized full MeshCore public key."""
    text = str(value or "").strip()
    return text.lower() if _PUBLIC_KEY_PATTERN.fullmatch(text) else None


def _is_contact_entity(entity: er.RegistryEntry) -> bool:
    """Identify MeshCore contact metadata without using a friendly name as identity."""
    metadata = "_".join(
        filter(
            None,
            (
                entity.unique_id,
                entity.translation_key,
                entity.original_name,
            ),
        )
    )
    return "contact" in _normalize(metadata).split("_")


def _identifier_prefixes(value: str, *, legacy: bool = False) -> set[str]:
    """Extract exact prefixes from structured or legacy identifier text."""
    normalized = value.strip()
    if prefix := _valid_prefix(normalized):
        return {prefix}
    if public_key := _valid_public_key(normalized):
        return {public_key[:12]}

    if not legacy:
        match = re.search(
            r"(?:^|_)(?:repeater|relay|contact)_"
            r"(?P<key>[0-9a-fA-F]{12}|[0-9a-fA-F]{64})$",
            normalized,
            re.IGNORECASE,
        )
        if match:
            key = match.group("key").lower()
            return {key[:12]}
        return set()

    return {token[:12].lower() for token in _HEX_TOKEN_PATTERN.findall(normalized)}


def _identifier_public_keys(value: str) -> set[str]:
    """Extract full keys from exact or structured MeshCore identifiers."""
    normalized = value.strip()
    if public_key := _valid_public_key(normalized):
        return {public_key}
    match = re.search(
        r"(?:^|_)(?:repeater|relay|contact)_"
        r"(?P<key>[0-9a-fA-F]{64})$",
        normalized,
        re.IGNORECASE,
    )
    return {match.group("key").lower()} if match else set()


def _resolution_at_source(
    source: str,
    prefixes: set[str],
    public_keys: set[str],
    checked: list[str],
    ambiguities: list[str],
) -> CommandAddressResolution | None:
    """Resolve unique evidence or record ambiguity and continue."""
    checked.append(source)
    prefixes.update(public_key[:12] for public_key in public_keys)
    if not prefixes:
        return None
    if len(prefixes) > 1:
        ambiguities.append(f"ambiguous {source}: multiple 12-character pubkey prefixes")
        return None
    public_key = next(iter(public_keys)) if len(public_keys) == 1 else None
    return CommandAddressResolution(
        public_key=public_key,
        pubkey_prefix=next(iter(prefixes)),
        resolution_source=source,
        resolution_sources_checked=tuple(checked),
    )


def _command_identity(
    hass: HomeAssistant,
    stable_id: str,
    device_identifiers: Iterable[tuple[str, str]],
    entities: Iterable[er.RegistryEntry],
) -> CommandAddressResolution:
    """Resolve one exact command prefix using ordered public registry evidence."""
    checked: list[str] = []
    ambiguities: list[str] = []
    entity_states = [(entity, hass.states.get(entity.entity_id)) for entity in entities]
    non_contact_states = [
        state
        for entity, state in entity_states
        if state is not None and not _is_contact_entity(entity)
    ]
    contact_states = [
        state
        for entity, state in entity_states
        if state is not None and _is_contact_entity(entity)
    ]

    result = _resolution_at_source(
        "explicit_pubkey_prefix",
        {
            prefix
            for state in non_contact_states
            if (prefix := _valid_prefix(state.attributes.get("pubkey_prefix")))
        },
        set(),
        checked,
        ambiguities,
    )
    if result:
        return result

    result = _resolution_at_source(
        "full_public_key",
        set(),
        {
            public_key
            for state in non_contact_states
            if (public_key := _valid_public_key(state.attributes.get("public_key")))
        },
        checked,
        ambiguities,
    )
    if result:
        return result

    result = _resolution_at_source(
        "contact_entity_pubkey_prefix",
        {
            prefix
            for state in contact_states
            if (prefix := _valid_prefix(state.attributes.get("pubkey_prefix")))
        },
        {
            public_key
            for state in contact_states
            if (public_key := _valid_public_key(state.attributes.get("public_key")))
        },
        checked,
        ambiguities,
    )
    if result:
        return result

    result = _resolution_at_source(
        "device_identifier",
        {
            prefix
            for domain, identifier in device_identifiers
            if domain == MESHCORE_DOMAIN
            for prefix in _identifier_prefixes(identifier)
        },
        {
            public_key
            for domain, identifier in device_identifiers
            if domain == MESHCORE_DOMAIN
            for public_key in _identifier_public_keys(identifier)
        },
        checked,
        ambiguities,
    )
    if result:
        return result

    result = _resolution_at_source(
        "source_entity_identifier",
        {
            prefix
            for entity, _state in entity_states
            for prefix in _identifier_prefixes(entity.unique_id, legacy=True)
        },
        set(),
        checked,
        ambiguities,
    )
    if result:
        return result

    result = _resolution_at_source(
        "legacy_stable_id",
        _identifier_prefixes(stable_id, legacy=True),
        set(),
        checked,
        ambiguities,
    )
    if result:
        return result

    return CommandAddressResolution(
        resolution_sources_checked=tuple(checked),
        rejection_reason=(
            "no unique 12-character pubkey prefix found after all resolution "
            f"sources; {'; '.join(ambiguities)}"
            if ambiguities
            else "no valid 12-character pubkey prefix found"
        ),
    )


async def async_discover_repeaters(hass: HomeAssistant) -> DiscoveryResult:
    """Discover MeshCore devices without modifying either registry."""
    meshcore_entries = tuple(
        sorted(
            entry.entry_id
            for entry in hass.config_entries.async_entries(MESHCORE_DOMAIN)
        )
    )
    if not meshcore_entries:
        return DiscoveryResult.create({}, (), ("MeshCore has no config entries.",))

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    entry_ids = set(meshcore_entries)
    warnings: list[str] = []
    repeaters: dict[str, DiscoveredSourceRepeater] = {}

    entities_by_device: dict[str, list[er.RegistryEntry]] = {}
    for entity in entity_registry.entities.values():
        if (
            entity.platform == MESHCORE_DOMAIN
            and entity.config_entry_id in entry_ids
            and entity.device_id
        ):
            entities_by_device.setdefault(entity.device_id, []).append(entity)

    for device in device_registry.devices.values():
        related_entries = sorted(set(device.config_entries) & entry_ids)
        owned_entities = entities_by_device.get(device.id, [])
        if not related_entries:
            continue

        stable_id = stable_identifier_from(device.identifiers)
        if stable_id is None:
            warnings.append(
                f"Skipped MeshCore device {device.id}: no MeshCore-owned stable identifier."
            )
            continue
        if stable_id in repeaters:
            warnings.append(
                f"Skipped duplicate MeshCore stable identifier on device {device.id}."
            )
            continue

        role_candidates: dict[str, list[_RoleCandidate]] = {}
        repeater_warnings: list[str] = []
        for entity in sorted(owned_entities, key=lambda item: item.entity_id):
            device_class, unit = _entity_metadata(hass, entity)
            candidate = _source_role_candidate(
                entity_id=entity.entity_id,
                unique_id=entity.unique_id,
                original_name=entity.original_name,
                translation_key=entity.translation_key,
                device_class=device_class,
                unit_of_measurement=unit,
                disabled=entity.disabled_by is not None,
            )
            if candidate is None:
                continue
            role_candidates.setdefault(candidate.role, []).append(candidate)

        selected_candidates: dict[str, _RoleCandidate] = {}
        for role, candidates in role_candidates.items():
            ranked = sorted(candidates, key=lambda item: (-item.score, item.entity_id))
            selected_candidates[role] = ranked[0]
            if len(ranked) > 1 and ranked[0].score == ranked[1].score:
                repeater_warnings.append(
                    f"Ambiguous {role} mapping between equally ranked registry "
                    f"entities; using {ranked[0].entity_id}."
                )

        role_entities = {
            role: candidate.entity_id for role, candidate in selected_candidates.items()
        }

        missing_roles = tuple(
            role for role in EXPECTED_SOURCE_ROLES if role not in role_entities
        )

        device_type, type_confidence, type_method = _classify_device_type(
            device, owned_entities
        )
        mapping_confidence, mapping_method = _mapping_summary(
            selected_candidates.values()
        )
        confidence_score = round(
            (mapping_confidence + type_confidence) / 2
            if type_confidence
            else mapping_confidence * 0.8
        )

        command_address = _command_identity(
            hass, stable_id, device.identifiers, owned_entities
        )
        repeaters[stable_id] = DiscoveredSourceRepeater(
            stable_id=stable_id,
            display_name=_device_name(device, stable_id),
            device_registry_id=device.id,
            meshcore_config_entry_id=related_entries[0],
            entities=SourceEntityMappings(
                voltage=role_entities.get("voltage"),
                battery_percentage=role_entities.get("battery_percentage"),
                airtime_utilisation=role_entities.get("airtime_utilisation"),
                availability=role_entities.get("availability"),
            ),
            missing=MissingSourceInformation(missing_roles),
            warnings=tuple(repeater_warnings),
            device_type=device_type,
            device_type_method=type_method,
            confidence_score=confidence_score,
            mapping_method=mapping_method,
            source_entity_count=len(owned_entities),
            public_key=command_address.public_key,
            pubkey_prefix=command_address.pubkey_prefix,
            command_address=command_address,
        )

    if not repeaters:
        warnings.append(
            "No registry devices with MeshCore ownership, stable identifiers, and "
            "linked entities were found."
        )
    _LOGGER.debug("Discovered %s MeshCore device candidates", len(repeaters))
    return DiscoveryResult.create(repeaters, meshcore_entries, tuple(warnings))
