"""Tests for the native MeshCore NOC development update entity."""

from __future__ import annotations

import json
import os
import stat
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientError, ClientResponseError
from awesomeversion import AwesomeVersion
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshcore_noc.const import (
    CONF_MANAGED_REPEATER_IDS,
    DOMAIN,
    INTEGRATION_VERSION,
    UPDATE_CHANNEL_DEVELOPMENT,
    UPDATE_CHANNEL_STABLE,
)
from custom_components.meshcore_noc.update import MeshCoreNocUpdateEntity
from custom_components.meshcore_noc.updater import (
    MAX_EXTRACTED_BYTES,
    REQUIRED_INTEGRATION_FILES,
    MeshCoreNocUpdateCoordinator,
    UpdateData,
    _async_get_development_update,
    _async_get_stable_update,
    _extract_validated_component,
    _install_archive,
    _prune_backups,
    _validate_manifest,
    version_is_newer,
)

from .helpers import add_meshcore_entry, add_repeater, setup_noc_entry


def _archive(
    version: str = "4.0.0-alpha3.3",
    *,
    domain: str = DOMAIN,
    extras: dict[str, tuple[bytes, int | None]] | None = None,
) -> bytes:
    """Build a minimal repository archive containing all required files."""
    stream = BytesIO()
    prefix = "MeshCore-NOC-v4-development/custom_components/meshcore_noc/"
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in REQUIRED_INTEGRATION_FILES:
            content = b"# test\n"
            if relative == "manifest.json":
                content = json.dumps({"domain": domain, "version": version}).encode()
            elif relative.endswith(".json"):
                content = b"{}"
            archive.writestr(prefix + relative, content)
        for name, (content, mode) in (extras or {}).items():
            info = zipfile.ZipInfo(name)
            if mode is not None:
                info.external_attr = mode << 16
            archive.writestr(info, content)
    return stream.getvalue()


def _installed_component(config_dir: Path, marker: str = "old") -> Path:
    """Create an installed component tree for replacement tests."""
    component = config_dir / "custom_components" / DOMAIN
    component.mkdir(parents=True)
    (component / "marker.txt").write_text(marker, encoding="utf-8")
    return component


def test_manifest_validation_and_prerelease_comparison() -> None:
    """Manifest identity is strict and AwesomeVersion orders prereleases."""
    _validate_manifest(
        {"domain": DOMAIN, "version": "4.0.0-alpha3.3"},
        "4.0.0-alpha3.3",
    )
    assert AwesomeVersion("4.0.0-alpha3.2") != AwesomeVersion("4.0.0-alpha3.3")
    assert version_is_newer("4.0.0-alpha3.3", "4.0.0-alpha3.2")
    with pytest.raises(ValueError, match="wrong domain"):
        _validate_manifest({"domain": "wrong", "version": "4.0.0-alpha3.3"})
    with pytest.raises(ValueError, match="valid version"):
        _validate_manifest({"domain": DOMAIN})
    with pytest.raises(ValueError, match="offered version"):
        _validate_manifest(
            {"domain": DOMAIN, "version": "4.0.0-alpha3.2"},
            "4.0.0-alpha3.3",
        )


async def test_update_check_match_newer_and_offline_retains_last(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checks expose matching/new versions and retain success when offline."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_DEVELOPMENT)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_json",
        AsyncMock(
            side_effect=[
                {"domain": DOMAIN, "version": INTEGRATION_VERSION},
                {"sha": "abc", "commit": {}},
                {"domain": DOMAIN, "version": "4.0.1"},
                {"sha": "def", "commit": {}},
            ]
        ),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_text",
        AsyncMock(return_value=f"## [{INTEGRATION_VERSION}]\n\n- Current."),
    )
    data = await coordinator._async_update_data()
    assert data.latest_version == INTEGRATION_VERSION
    entity = MeshCoreNocUpdateEntity(coordinator)
    coordinator.data = data
    assert not entity.version_is_newer(data.latest_version, entity.installed_version)

    newer = "4.0.1"
    coordinator.data = await coordinator._async_update_data()
    assert entity.version_is_newer(newer, entity.installed_version)

    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_development_update",
        AsyncMock(side_effect=ClientError("offline")),
    )
    retained = await coordinator._async_update_data()
    assert retained.latest_version == newer
    assert coordinator.last_check_error == "ClientError"


async def test_rate_limit_is_concise_and_non_destructive(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A GitHub rate-limit response retains the last successful result."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    coordinator.data = UpdateData(latest_version="4.0.0-alpha3.4")
    error = ClientResponseError(
        request_info=AsyncMock(),
        history=(),
        status=403,
        message="rate limited with sensitive response details",
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(side_effect=error),
    )
    assert (await coordinator._async_update_data()).latest_version == "4.0.0-alpha3.4"
    assert coordinator.last_check_error == "GitHub returned HTTP 403"


async def test_stable_ignores_drafts_and_prereleases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stable selects the first published production release."""
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_json_value",
        AsyncMock(
            return_value=[
                {"draft": True, "tag_name": "v9.0.0"},
                {"prerelease": True, "tag_name": "v8.0.0"},
                {
                    "draft": False,
                    "prerelease": False,
                    "tag_name": "v4.1.0",
                    "name": "MeshCore NOC 4.1",
                    "body": "Production notes",
                    "html_url": "https://github.com/Jacolrsa/MeshCore-NOC/releases/tag/v4.1.0",
                    "zipball_url": "https://api.github.com/repos/Jacolrsa/MeshCore-NOC/zipball/v4.1.0",
                },
            ]
        ),
    )

    data = await _async_get_stable_update(object())

    assert data.latest_version == "4.1.0"
    assert data.release_summary == "MeshCore NOC 4.1"
    assert data.release_notes == "Production notes"
    assert data.release_url.endswith("/releases/tag/v4.1.0")
    assert data.source_url_type == "github_release_api"


async def test_stable_handles_no_valid_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty stable channel remains unknown instead of up-to-date."""
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_json_value",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(ValueError, match="No valid stable"):
        await _async_get_stable_update(object())


async def test_development_reads_manifest_and_commit_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development uses the branch manifest version and commit metadata."""
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_json",
        AsyncMock(
            side_effect=[
                {"domain": DOMAIN, "version": "4.0.0-alpha5.0"},
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Alpha5 dashboard",
                        "author": {"date": "2026-07-27T10:00:00Z"},
                    },
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_text",
        AsyncMock(return_value="## [4.0.0-alpha5.0]\n\n- Dashboard."),
    )

    data = await _async_get_development_update(object())

    assert data.latest_version == "4.0.0-alpha5.0"
    assert data.branch == "v4-development"
    assert data.commit_sha == "abc123"
    assert data.commit_message == "Alpha5 dashboard"
    assert data.commit_timestamp == "2026-07-27T10:00:00Z"
    assert data.release_url.endswith("/commit/abc123")


def test_version_comparison_handles_channel_examples_and_malformed() -> None:
    """AwesomeVersion plus project alpha ordering never compares lexically."""
    assert version_is_newer("4.0.0-alpha5.0", "4.0.0-alpha4.2")
    assert not version_is_newer("4.0.0-alpha5.0", "4.0.0-alpha5.0")
    assert version_is_newer("4.1.0", "4.0.0")
    assert not version_is_newer("not-a-version", "4.0.0")


async def test_timeout_retains_cached_success(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temporary timeout preserves the last successful remote result."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    coordinator.data = UpdateData(
        latest_version="4.1.0",
        release_url="https://github.com/Jacolrsa/MeshCore-NOC/releases/tag/v4.1.0",
        source_url_type="github_release_api",
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(side_effect=TimeoutError),
    )

    retained = await coordinator._async_update_data()

    assert retained.latest_version == "4.1.0"
    assert coordinator.last_check_error == "TimeoutError"


@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (b"not-a-zip", "valid ZIP"),
        (_archive(domain="wrong"), "wrong domain"),
        (_archive(version="4.0.0-alpha3.2"), "offered version"),
        (
            _archive(
                extras={
                    "../escape": (b"bad", None),
                }
            ),
            "unsafe path",
        ),
        (
            _archive(
                extras={
                    "MeshCore-NOC-v4-development/unsafe-link": (
                        b"../../outside",
                        stat.S_IFLNK | 0o777,
                    ),
                }
            ),
            "symbolic link",
        ),
    ],
)
def test_archive_validation_rejects_untrusted_content(
    tmp_path: Path, archive: bytes, message: str
) -> None:
    """Malformed, mismatched, traversing, and symlink archives are rejected."""
    with pytest.raises(ValueError, match=message):
        _extract_validated_component(
            archive,
            tmp_path / "extract",
            "4.0.0-alpha3.3",
        )


def test_oversized_expanded_archive_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expanded content is bounded independently of compressed size."""
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.MAX_EXTRACTED_BYTES",
        10,
    )
    assert MAX_EXTRACTED_BYTES > 10
    with pytest.raises(ValueError, match="too large"):
        _extract_validated_component(
            _archive(),
            tmp_path / "extract",
            "4.0.0-alpha3.3",
        )


def test_successful_install_creates_backup_and_replaces_tree(tmp_path: Path) -> None:
    """A valid archive is staged, backed up, and installed."""
    installed = _installed_component(tmp_path)
    result = _install_archive(tmp_path, _archive(), "4.0.0-alpha3.3")
    assert (
        result.backup_path.joinpath("marker.txt").read_text(encoding="utf-8") == "old"
    )
    assert installed.joinpath("manifest.json").is_file()
    assert not installed.joinpath("marker.txt").exists()
    assert result.installed_manifest_version == "4.0.0-alpha3.3"


def test_validation_failure_leaves_install_untouched(tmp_path: Path) -> None:
    """Failure before replacement cannot alter installed files."""
    installed = _installed_component(tmp_path)
    with pytest.raises(ValueError):
        _install_archive(tmp_path, b"broken", "4.0.0-alpha3.3")
    assert installed.joinpath("marker.txt").read_text(encoding="utf-8") == "old"


def test_replacement_failure_restores_installed_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure after moving the old tree restores it automatically."""
    installed = _installed_component(tmp_path)
    real_replace = os.replace
    calls = 0

    def _fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.os.replace", _fail_second_replace
    )
    with pytest.raises(OSError, match="simulated"):
        _install_archive(tmp_path, _archive(), "4.0.0-alpha3.3")
    assert installed.joinpath("marker.txt").read_text(encoding="utf-8") == "old"


def test_only_five_newest_backups_are_retained(tmp_path: Path) -> None:
    """Backup retention removes only older integration backups."""
    backups = tmp_path / "meshcore_noc_backups"
    backups.mkdir()
    for index in range(7):
        (backups / f"2026010{index}T000000Z-version").mkdir()
    _prune_backups(backups)
    assert len(list(backups.iterdir())) == 5
    assert not (backups / "20260100T000000Z-version").exists()


async def test_concurrent_install_is_rejected(hass: HomeAssistant) -> None:
    """Only one installation may hold the coordinator install lock."""
    coordinator = MeshCoreNocUpdateCoordinator(hass)
    coordinator.data = UpdateData(latest_version="4.0.0-alpha3.3")
    await coordinator._install_lock.acquire()
    try:
        with pytest.raises(HomeAssistantError, match="already in progress"):
            await coordinator.async_install_latest()
    finally:
        coordinator._install_lock.release()


async def test_restart_required_notification_does_not_change_loaded_version(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staged update notifies before restart and keeps the loaded version."""
    coordinator = MeshCoreNocUpdateCoordinator(hass)
    coordinator.data = UpdateData(latest_version="4.0.0-alpha3.4")
    coordinator.installation_state = "restart_required"
    create_notification = Mock()
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.persistent_notification.async_create",
        create_notification,
    )
    monkeypatch.setattr(
        type(hass.services),
        "has_service",
        lambda registry, domain, service: False,
    )

    await coordinator._async_request_restart()

    create_notification.assert_called_once()
    assert coordinator.installation_state == "restart_required"
    assert MeshCoreNocUpdateEntity(coordinator).installed_version == INTEGRATION_VERSION


async def test_update_entity_is_only_on_controller_and_keeps_loaded_version(
    hass: HomeAssistant,
) -> None:
    """The update entity belongs to the controller and never to repeaters."""
    meshcore_entry = add_meshcore_entry(hass)
    add_repeater(hass, meshcore_entry, stable_id="node-a")
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["node-a"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    update_entry = entity_registry.async_get("update.meshcore_noc_update")
    controller = device_registry.async_get_device(identifiers={(DOMAIN, "noc")})
    repeater = device_registry.async_get_device(identifiers={(DOMAIN, "node-a")})
    assert update_entry is not None
    assert controller is not None
    assert repeater is not None
    assert update_entry.device_id == controller.id
    assert update_entry.device_id != repeater.id
    assert noc_entry.runtime_data.update_coordinator is not None
    assert (
        hass.states.get("update.meshcore_noc_update").attributes["installed_version"]
        == INTEGRATION_VERSION
    )


async def test_install_action_does_not_touch_repeaters_or_user_helpers(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entity install action is isolated from Home Assistant registries."""
    meshcore_entry = add_meshcore_entry(hass)
    upstream_device, _ = add_repeater(
        hass,
        meshcore_entry,
        stable_id="protected-repeater",
    )
    noc_entry = MockConfigEntry(
        domain=DOMAIN,
        title="MeshCore NOC",
        options={CONF_MANAGED_REPEATER_IDS: ["protected-repeater"]},
    )
    noc_entry.add_to_hass(hass)
    await setup_noc_entry(hass, noc_entry)
    registry = er.async_get(hass)
    helper = registry.async_get_or_create(
        domain="input_number",
        platform="input_number",
        unique_id="user-calibration-helper",
    )
    managed_device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "protected-repeater")}
    )
    assert managed_device is not None

    coordinator = noc_entry.runtime_data.update_coordinator
    coordinator.data = UpdateData(latest_version="4.0.0-alpha3.4")
    install = AsyncMock()
    monkeypatch.setattr(coordinator, "async_install_latest", install)
    await MeshCoreNocUpdateEntity(coordinator).async_install(None, False)

    install.assert_awaited_once()
    assert dr.async_get(hass).async_get(upstream_device.id) is not None
    assert dr.async_get(hass).async_get(managed_device.id) is not None
    assert registry.async_get(helper.entity_id) is not None


async def test_patch_alpha_update_is_installable(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A patch-level Alpha iteration produces an installable update state."""
    monkeypatch.setattr(
        "custom_components.meshcore_noc.update.INTEGRATION_VERSION",
        "4.0.0-alpha5.2",
    )
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_DEVELOPMENT)
    coordinator.data = UpdateData(latest_version="4.0.0-alpha5.2.1")
    entity = MeshCoreNocUpdateEntity(coordinator)

    assert entity.state == "on"
    assert entity.supported_features == 17

    install = AsyncMock()
    monkeypatch.setattr(coordinator, "async_install_latest", install)
    await entity.async_install(None, False)
    install.assert_awaited_once_with()
