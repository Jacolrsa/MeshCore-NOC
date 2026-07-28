"""Tests for per-repeater Clock Intelligence buttons."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_platform

if not hasattr(entity_platform, "AddConfigEntryEntitiesCallback"):
    entity_platform.AddConfigEntryEntitiesCallback = Any

from custom_components.meshcore_noc.button import MeshCoreNocCheckClockButton


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """Keep the focused entity delegation test independent of HA setup."""
    yield


@pytest.mark.asyncio
async def test_check_clock_button_delegates_stable_id_to_clock_manager() -> None:
    """The device button reuses the existing Clock Manager path."""
    button = object.__new__(MeshCoreNocCheckClockButton)
    button.coordinator = SimpleNamespace(
        source=SimpleNamespace(stable_id="noc-stable-laguna")
    )
    button.clock_manager = SimpleNamespace(async_check_clock=AsyncMock())

    await button.async_press()

    button.clock_manager.async_check_clock.assert_awaited_once_with("noc-stable-laguna")
