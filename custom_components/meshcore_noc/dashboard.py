"""Automatic Home Assistant dashboard support for MeshCore NOC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.persistent_notification import async_create
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from .const import DOMAIN, INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)

DASHBOARD_TITLE = "MeshCore NOC"
DASHBOARD_URL_PATH = "meshcore-noc"
DASHBOARD_ICON = "mdi:access-point-network"
STRATEGY_TYPE = "custom:meshcore-noc"
STATIC_URL = "/api/meshcore_noc/frontend/meshcore-noc-dashboard.js"
RESOURCE_URL = f"{STATIC_URL}?v={INTEGRATION_VERSION}"
PATCH_STATIC_URL = "/api/meshcore_noc/frontend/meshcore-noc-dashboard-patch.js"
PATCH_RESOURCE_URL = f"{PATCH_STATIC_URL}?v={INTEGRATION_VERSION}"

_FRONTEND_REGISTERED = "dashboard_frontend_registered"
_STATIC_PATH_REGISTERED = "dashboard_static_path_registered"
_NOTIFICATION_ID = "meshcore_noc_dashboard_setup"


@dataclass(frozen=True, slots=True)
class DashboardSetupResult:
    """Describe dashboard setup without exposing Home Assistant internals."""

    frontend_registered: bool
    dashboard_status: str


async def async_setup_dashboard(hass: HomeAssistant) -> DashboardSetupResult:
    """Register the frontend bundle and ensure the dashboard exists."""
    frontend_registered = await _async_register_frontend(hass)
    if not frontend_registered:
        _notify_manual_creation(
            hass,
            "The MeshCore NOC frontend resource could not be registered, so "
            "dashboard setup cannot continue safely.",
            resource_registered=False,
        )
        return DashboardSetupResult(False, "resource_registration_unavailable")
    dashboard_status = await _async_ensure_dashboard(hass)
    return DashboardSetupResult(frontend_registered, dashboard_status)


async def _async_register_frontend(hass: HomeAssistant) -> bool:
    """Serve the bundle and persist its Lovelace modules globally."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_FRONTEND_REGISTERED):
        _LOGGER.debug("MeshCore NOC frontend module resources already registered")
        return True

    if not await async_setup_component(hass, "frontend", {}):
        _LOGGER.warning("MeshCore NOC frontend resource registration unavailable")
        return False

    if not domain_data.get(_STATIC_PATH_REGISTERED):
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL,
                    str(frontend_dir / "meshcore-noc-dashboard.js"),
                    cache_headers=True,
                ),
                StaticPathConfig(
                    PATCH_STATIC_URL,
                    str(frontend_dir / "meshcore-noc-dashboard-patch.js"),
                    cache_headers=True,
                ),
            ]
        )
        domain_data[_STATIC_PATH_REGISTERED] = True
        _LOGGER.info(
            "MeshCore NOC dashboard static paths registered: %s, %s",
            STATIC_URL,
            PATCH_STATIC_URL,
        )

    if "lovelace" not in hass.data:
        await async_setup_component(hass, "lovelace", {})
    lovelace_data: Any = hass.data.get("lovelace")
    resources = (
        lovelace_data.get("resources")
        if isinstance(lovelace_data, dict)
        else getattr(lovelace_data, "resources", None)
    )
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.warning(
            "MeshCore NOC Lovelace resource collection is unavailable; "
            "the served files alone are not a frontend loader"
        )
        return False

    try:
        if hasattr(resources, "async_get_info"):
            await resources.async_get_info()
        for static_url, resource_url in (
            (STATIC_URL, RESOURCE_URL),
            (PATCH_STATIC_URL, PATCH_RESOURCE_URL),
        ):
            existing = next(
                (
                    item
                    for item in resources.async_items()
                    if _resource_base_url(item.get("url")) == static_url
                ),
                None,
            )
            if existing is None:
                await resources.async_create_item(
                    {"res_type": "module", "url": resource_url}
                )
                _LOGGER.info(
                    "MeshCore NOC Lovelace module resource created: %s",
                    resource_url,
                )
            elif existing.get("url") != resource_url or existing.get("type") != "module":
                await resources.async_update_item(
                    existing["id"],
                    {"res_type": "module", "url": resource_url},
                )
                _LOGGER.info(
                    "MeshCore NOC Lovelace module resource updated: %s",
                    resource_url,
                )
            else:
                _LOGGER.debug(
                    "MeshCore NOC Lovelace module resource already registered: %s",
                    resource_url,
                )
    except (HomeAssistantError, vol.Invalid, KeyError, RuntimeError, ValueError) as err:
        _LOGGER.warning(
            "MeshCore NOC Lovelace module resource registration failed: %s", err
        )
        return False

    domain_data[_FRONTEND_REGISTERED] = True
    _LOGGER.info(
        "MeshCore NOC frontend loading mechanism selected: Lovelace module resources"
    )
    return True


def _resource_base_url(url: Any) -> str | None:
    """Return a resource URL without its cache-busting query string."""
    return url.partition("?")[0] if isinstance(url, str) else None


async def _async_ensure_dashboard(hass: HomeAssistant) -> str:
    """Create the strategy dashboard with Lovelace's storage collection API."""
    _LOGGER.debug("MeshCore NOC dashboard creation check attempted")
    if "lovelace" not in hass.data:
        await async_setup_component(hass, "lovelace", {})

    lovelace_data: Any = hass.data.get("lovelace")
    if not lovelace_data:
        _notify_manual_creation(hass, "Lovelace is not available.")
        return "manual_creation_required"

    if isinstance(lovelace_data, dict):
        dashboards = lovelace_data.get("dashboards")
        collection = lovelace_data.get("dashboards_collection")
    else:
        dashboards = getattr(lovelace_data, "dashboards", None)
        collection = getattr(lovelace_data, "dashboards_collection", None)
    if not isinstance(dashboards, dict) or collection is None:
        _notify_manual_creation(
            hass,
            "This Home Assistant dashboard mode does not expose the dashboard "
            "collection API.",
        )
        return "manual_creation_required"

    existing = dashboards.get(DASHBOARD_URL_PATH)
    if existing is not None:
        try:
            config = await existing.async_load(False)
        except (HomeAssistantError, OSError, ValueError) as err:
            _notify_manual_creation(
                hass,
                f"The existing {DASHBOARD_URL_PATH!r} dashboard could not be "
                f"identified safely: {err}",
            )
            return "url_path_collision"
        if _is_meshcore_dashboard(config):
            return "existing"
        _notify_manual_creation(
            hass,
            f"The URL path {DASHBOARD_URL_PATH!r} is already used by another "
            "dashboard.",
        )
        return "url_path_collision"

    try:
        _LOGGER.debug("MeshCore NOC dashboard creation attempted")
        await collection.async_create_item(
            {
                "url_path": DASHBOARD_URL_PATH,
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
            }
        )
        dashboard = dashboards[DASHBOARD_URL_PATH]
        await dashboard.async_save({"strategy": {"type": STRATEGY_TYPE}})
    except (HomeAssistantError, vol.Invalid, KeyError, RuntimeError, ValueError) as err:
        _LOGGER.warning("Unable to create the MeshCore NOC dashboard: %s", err)
        _notify_manual_creation(hass, str(err))
        return "manual_creation_required"

    _LOGGER.info("MeshCore NOC dashboard creation succeeded")
    return "created"


def _is_meshcore_dashboard(config: Any) -> bool:
    """Return whether a stored dashboard uses our stable strategy identity."""
    return (
        isinstance(config, dict)
        and isinstance(config.get("strategy"), dict)
        and config["strategy"].get("type") == STRATEGY_TYPE
    )


def _notify_manual_creation(
    hass: HomeAssistant, reason: str, *, resource_registered: bool = True
) -> None:
    """Provide the one safe fallback step without touching .storage directly."""
    registration = (
        "The MeshCore NOC frontend resource has been registered. "
        if resource_registered
        else ""
    )
    async_create(
        hass,
        (
            f"{reason}\n\n{registration}Restart Home Assistant Core, hard-refresh "
            "the browser, then select MeshCore NOC in Settings → Dashboards → "
            "Add dashboard. If needed, create it with URL path "
            f"`{DASHBOARD_URL_PATH}` and strategy type `{STRATEGY_TYPE}`."
        ),
        title="MeshCore NOC dashboard needs one setup step",
        notification_id=_NOTIFICATION_ID,
    )
    _LOGGER.debug("MeshCore NOC dashboard fallback notification created")
