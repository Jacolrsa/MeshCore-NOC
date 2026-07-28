"""Shared Home Assistant test fixtures."""

import os

import pytest
import pytest_socket

from custom_components.meshcore_noc.dashboard import DashboardSetupResult
from custom_components.meshcore_noc.updater import MeshCoreNocUpdateCoordinator

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Allow Home Assistant to load this repository's custom integration."""
    if request.node.path.name != "test_branding.py":
        request.getfixturevalue("enable_custom_integrations")
    yield


@pytest.fixture(autouse=True)
def disable_live_update_checks(monkeypatch):
    """Keep integration tests deterministic and offline."""

    async def _async_refresh_without_network(
        coordinator: MeshCoreNocUpdateCoordinator,
    ) -> None:
        return None

    monkeypatch.setattr(
        MeshCoreNocUpdateCoordinator,
        "async_refresh",
        _async_refresh_without_network,
    )


@pytest.fixture(autouse=True)
def isolate_dashboard_setup(monkeypatch):
    """Keep entry tests independent of a configured Lovelace frontend."""

    async def _async_setup_dashboard(_hass):
        return DashboardSetupResult(False, "test")

    monkeypatch.setattr(
        "custom_components.meshcore_noc.async_setup_dashboard",
        _async_setup_dashboard,
    )


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup():
    """Allow the local socket pair required by Windows asyncio event loops."""
    yield
    if os.name == "nt":
        pytest_socket.enable_socket()


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(fixturedef) -> None:
    """Enable sockets before pytest-asyncio creates the Windows event loop."""
    if os.name == "nt" and fixturedef.argname == "event_loop":
        pytest_socket.enable_socket()
