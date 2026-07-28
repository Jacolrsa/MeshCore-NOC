"""Tests for automatic MeshCore NOC dashboard setup."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.meshcore_noc.dashboard import (
    DASHBOARD_URL_PATH,
    RESOURCE_URL,
    STATIC_URL,
    STRATEGY_TYPE,
    _async_ensure_dashboard,
    _async_register_frontend,
    async_setup_dashboard,
)


class FakeDashboard:
    """Minimal Lovelace storage dashboard."""

    def __init__(self, config):
        self.config = config
        self.async_save = AsyncMock(side_effect=self._save)

    async def async_load(self, _force):
        return self.config

    async def _save(self, config):
        self.config = config


class FakeCollection:
    """Minimal dashboard collection that mirrors Home Assistant creation."""

    def __init__(self, dashboards):
        self.dashboards = dashboards
        self.async_create_item = AsyncMock(side_effect=self._create)

    async def _create(self, data):
        self.dashboards[data["url_path"]] = FakeDashboard(None)


class FakeResources:
    """Minimal Lovelace resource storage collection."""

    def __init__(self, items=None):
        self._items = list(items or [])
        self.async_get_info = AsyncMock()
        self.async_create_item = AsyncMock(side_effect=self._create)
        self.async_update_item = AsyncMock(side_effect=self._update)

    def async_items(self):
        return list(self._items)

    async def _create(self, data):
        self._items.append(
            {
                "id": str(len(self._items) + 1),
                "type": data["res_type"],
                "url": data["url"],
            }
        )

    async def _update(self, item_id, data):
        item = next(item for item in self._items if item["id"] == item_id)
        item.update({"type": data["res_type"], "url": data["url"]})


@pytest.mark.asyncio
async def test_frontend_registration_is_cache_safe(monkeypatch):
    """The static path and global Lovelace module are registered once."""
    resources = FakeResources()
    hass = Mock()
    hass.data = {"lovelace": {"resources": resources}}
    hass.http.async_register_static_paths = AsyncMock()
    setup_component = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.dashboard.async_setup_component",
        setup_component,
    )

    assert await _async_register_frontend(hass)
    assert await _async_register_frontend(hass)

    registration = hass.http.async_register_static_paths.call_args.args[0][0]
    assert registration.url_path == STATIC_URL
    assert Path(registration.path).name == "meshcore-noc-dashboard.js"
    assert Path(registration.path).is_file()
    assert registration.cache_headers
    assert RESOURCE_URL.startswith(f"{STATIC_URL}?v=")
    assert RESOURCE_URL.endswith("?v=1.0.0")
    resources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": RESOURCE_URL}
    )
    setup_component.assert_awaited_once_with(hass, "frontend", {})


@pytest.mark.asyncio
async def test_module_registration_updates_old_query_without_duplicate(monkeypatch):
    """An existing Alpha4 resource is updated instead of duplicated."""
    resources = FakeResources(
        [{"id": "old", "type": "module", "url": f"{STATIC_URL}?v=4.0.0-alpha4.1"}]
    )
    hass = Mock()
    hass.data = {"lovelace": {"resources": resources}}
    hass.http.async_register_static_paths = AsyncMock()
    monkeypatch.setattr(
        "custom_components.meshcore_noc.dashboard.async_setup_component",
        AsyncMock(return_value=True),
    )

    assert await _async_register_frontend(hass)

    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_awaited_once_with(
        "old", {"res_type": "module", "url": RESOURCE_URL}
    )
    assert len(resources.async_items()) == 1


@pytest.mark.asyncio
async def test_module_registration_retries_without_duplicate_static_path(monkeypatch):
    """A temporary module-registration failure can retry safely."""
    resources = FakeResources()
    resources.async_create_item.side_effect = [RuntimeError("not ready"), None]
    hass = Mock()
    hass.data = {"lovelace": {"resources": resources}}
    hass.http.async_register_static_paths = AsyncMock()
    monkeypatch.setattr(
        "custom_components.meshcore_noc.dashboard.async_setup_component",
        AsyncMock(return_value=True),
    )

    assert not await _async_register_frontend(hass)
    assert await _async_register_frontend(hass)

    hass.http.async_register_static_paths.assert_awaited_once()
    assert resources.async_create_item.await_count == 2


@pytest.mark.asyncio
async def test_served_file_without_global_loader_is_failure(monkeypatch):
    """A static HTTP route alone does not count as frontend execution."""
    hass = Mock()
    hass.data = {"lovelace": {}}
    hass.http.async_register_static_paths = AsyncMock()
    monkeypatch.setattr(
        "custom_components.meshcore_noc.dashboard.async_setup_component",
        AsyncMock(return_value=True),
    )

    assert not await _async_register_frontend(hass)
    hass.http.async_register_static_paths.assert_awaited_once()


@pytest.mark.asyncio
async def test_dashboard_created_once_and_reused():
    """First setup creates one strategy dashboard; reload preserves it."""
    dashboards = {}
    collection = FakeCollection(dashboards)
    hass = Mock()
    hass.data = {
        "lovelace": {
            "dashboards": dashboards,
            "dashboards_collection": collection,
        }
    }

    assert await _async_ensure_dashboard(hass) == "created"
    assert dashboards[DASHBOARD_URL_PATH].config == {
        "strategy": {"type": STRATEGY_TYPE}
    }
    assert await _async_ensure_dashboard(hass) == "existing"
    collection.async_create_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_dashboard_url_collision_is_never_overwritten(monkeypatch):
    """A user dashboard at the stable path remains untouched."""
    existing = FakeDashboard({"views": []})
    collection = FakeCollection({DASHBOARD_URL_PATH: existing})
    hass = Mock()
    hass.data = {
        "lovelace": {
            "dashboards": {DASHBOARD_URL_PATH: existing},
            "dashboards_collection": collection,
        }
    }
    notify = Mock()
    monkeypatch.setattr("custom_components.meshcore_noc.dashboard.async_create", notify)

    assert await _async_ensure_dashboard(hass) == "url_path_collision"
    collection.async_create_item.assert_not_awaited()
    existing.async_save.assert_not_awaited()
    notify.assert_called_once()


@pytest.mark.asyncio
async def test_unsupported_lovelace_mode_gives_safe_fallback(monkeypatch):
    """No storage API means one notification and no direct storage edit."""
    hass = Mock()
    hass.data = {"lovelace": {}}
    notify = Mock()
    monkeypatch.setattr("custom_components.meshcore_noc.dashboard.async_create", notify)

    assert await _async_ensure_dashboard(hass) == "manual_creation_required"
    notify.assert_called_once()
    message = notify.call_args.args[1]
    assert "frontend resource has been registered" in message
    assert "strategy is loaded" not in message


@pytest.mark.asyncio
async def test_resource_registration_unavailable_is_truthful(monkeypatch):
    """A backend failure never claims browser-side strategy execution."""
    hass = Mock()
    notify = Mock()
    monkeypatch.setattr(
        "custom_components.meshcore_noc.dashboard._async_register_frontend",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr("custom_components.meshcore_noc.dashboard.async_create", notify)

    result = await async_setup_dashboard(hass)

    assert not result.frontend_registered
    assert result.dashboard_status == "resource_registration_unavailable"
    message = notify.call_args.args[1]
    assert "could not be registered" in message
    assert "resource has been registered" not in message
    assert "strategy is loaded" not in message


def test_dashboard_files_are_in_update_payload():
    """The native updater retains every dashboard runtime file."""
    from custom_components.meshcore_noc.updater import REQUIRED_INTEGRATION_FILES

    assert "dashboard.py" in REQUIRED_INTEGRATION_FILES
    assert "frontend/meshcore-noc-dashboard.js" in REQUIRED_INTEGRATION_FILES
