"""Tests for managed-device calculations and freshness thresholds."""

import pytest

from custom_components.meshcore_noc.coordinator import _freshness, calculate_health


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (0, "Fresh"),
        (4_499, "Fresh"),
        (4_500, "Aging"),
        (7_199, "Aging"),
        (7_200, "Stale"),
        (10_799, "Stale"),
        (10_800, "Offline"),
    ],
)
def test_freshness_transitions_over_time(age_seconds: int, expected: str) -> None:
    """Freshness changes at the production dashboard thresholds."""
    assert _freshness(age_seconds, True) == expected


def test_per_repeater_freshness_thresholds() -> None:
    """Configured ages override defaults without changing status semantics."""
    assert _freshness(100, True, 60, 120, 180) == "Aging"
    assert _freshness(150, True, 60, 120, 180) == "Stale"
    assert _freshness(180, True, 60, 120, 180) == "Offline"


def test_unavailable_source_is_offline() -> None:
    """Availability overrides telemetry age."""
    assert _freshness(0, False) == "Offline"
    assert _freshness(None, True) == "Offline"


@pytest.mark.parametrize(
    ("battery", "freshness", "expected"),
    [
        (None, "Fresh", "Unknown"),
        (100, "Fresh", "Excellent"),
        (79, "Fresh", "Good"),
        (100, "Aging", "Good"),
        (39, "Fresh", "Fair"),
        (100, "Stale", "Fair"),
        (19, "Fresh", "Poor"),
        (100, "Offline", "Poor"),
    ],
)
def test_health_isolated_from_entity_presentation(
    battery: int | None, freshness: str, expected: str
) -> None:
    """Health remains a focused replaceable calculation."""
    assert calculate_health(battery, freshness) == expected


def test_per_repeater_battery_thresholds() -> None:
    """Configured warning and critical values feed health consistently."""
    assert calculate_health(29, "Fresh", 50, 30) == "Poor"
    assert calculate_health(49, "Fresh", 50, 30) == "Fair"
