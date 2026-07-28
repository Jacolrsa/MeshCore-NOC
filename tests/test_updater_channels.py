"""Focused tests for update-channel remote metadata."""

from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientError, ClientResponseError
from homeassistant.core import HomeAssistant

from custom_components.meshcore_noc.const import (
    DOMAIN,
    UPDATE_CHANNEL_STABLE,
)
from custom_components.meshcore_noc.updater import (
    STABLE_RELEASES_URL,
    MeshCoreNocUpdateCoordinator,
    NoStableReleaseError,
    UpdateData,
    UpdateMetadataError,
    _async_get_development_update,
    _async_get_stable_update,
    _async_get_text,
    version_is_newer,
)


class _ResponseContext:
    """Minimal aiohttp response context for URL-validation tests."""

    def __init__(self, response: Mock) -> None:
        self.response = response

    async def __aenter__(self) -> Mock:
        return self.response

    async def __aexit__(self, *args: object) -> None:
        return None


async def test_github_api_response_url_is_trusted() -> None:
    """The Releases API response is not rejected after a successful request."""
    response = Mock()
    response.url = STABLE_RELEASES_URL
    response.raise_for_status = Mock()
    response.text = AsyncMock(return_value="[]")
    session = Mock()
    session.get.return_value = _ResponseContext(response)

    assert await _async_get_text(session, STABLE_RELEASES_URL) == "[]"
    response.raise_for_status.assert_called_once_with()


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
                    "html_url": (
                        "https://github.com/Jacolrsa/MeshCore-NOC/releases/tag/v4.1.0"
                    ),
                    "zipball_url": (
                        "https://api.github.com/repos/Jacolrsa/"
                        "MeshCore-NOC/zipball/v4.1.0"
                    ),
                },
            ]
        ),
    )

    data = await _async_get_stable_update(object())

    assert data.latest_version == "4.1.0"
    assert data.release_summary == "MeshCore NOC 4.1"
    assert data.release_url is not None
    assert data.release_url.endswith("/releases/tag/v4.1.0")


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
    assert data.commit_url is not None
    assert data.commit_url.endswith("/commit/abc123")


def test_version_comparison_is_robust() -> None:
    """Project alpha and stable versions are parsed rather than compared as text."""
    assert version_is_newer("4.0.0-alpha5.0", "4.0.0-alpha4.2")
    assert version_is_newer("4.0.0-alpha5.2.1", "4.0.0-alpha5.2")
    assert not version_is_newer("4.0.0-alpha5.2", "4.0.0-alpha5.2.1")
    assert version_is_newer("4.0.0-alpha5.3", "4.0.0-alpha5.2.9")
    assert version_is_newer("4.0.0-alpha6.0", "4.0.0-alpha5.99.99")
    assert version_is_newer("4.0.0-alpha5.2.1.3", "4.0.0-alpha5.2.1")
    assert not version_is_newer("4.0.0-alpha5.2.1", "4.0.0-alpha5.2.1")
    assert not version_is_newer("4.0.0-alpha5.0", "4.0.0-alpha5.0")
    assert version_is_newer("4.1.0", "4.0.0")
    assert not version_is_newer("4.0.0", "4.1.0")
    assert not version_is_newer("not-a-version", "4.0.0")


async def test_timeout_and_rate_limit_retain_cached_success(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Temporary GitHub failures preserve the last successful result."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    coordinator.data = UpdateData(
        latest_version="4.1.0",
        release_url=("https://github.com/Jacolrsa/MeshCore-NOC/releases/tag/v4.1.0"),
        source_url_type="github_release_api",
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    fetch = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        fetch,
    )
    assert (await coordinator._async_update_data()).latest_version == "4.1.0"
    assert coordinator.last_check_error == "TimeoutError"

    fetch.side_effect = ClientResponseError(
        request_info=AsyncMock(),
        history=(),
        status=403,
        message="rate limited",
    )
    assert (await coordinator._async_update_data()).latest_version == "4.1.0"
    assert coordinator.last_check_error == "GitHub returned HTTP 403"


async def test_offline_before_first_success_stays_unknown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never-checked and failed states do not claim up-to-date."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(side_effect=ClientError("offline")),
    )

    result = await coordinator._async_update_data()

    assert result.latest_version is None
    assert coordinator.last_successful_check is None
    assert coordinator.last_check_time is not None
    assert coordinator.last_check_error == "ClientError"


async def test_no_stable_release_clears_previous_latest(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authoritative empty release result is unknown, not cached up-to-date."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    coordinator.data = UpdateData(latest_version="4.1.0")
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(side_effect=NoStableReleaseError("none")),
    )

    result = await coordinator._async_update_data()

    assert result.latest_version is None
    assert coordinator.last_successful_check is not None
    assert coordinator.last_check_error == "No stable release available"


async def test_unexpected_github_payload_is_unknown_and_logged_at_debug(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed GitHub metadata becomes Unknown without masking other errors."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    coordinator.data = UpdateData(latest_version="4.1.0")
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(
            side_effect=UpdateMetadataError(
                "GitHub releases response is not a list"
            )
        ),
    )

    with caplog.at_level("DEBUG", logger="custom_components.meshcore_noc.updater"):
        result = await coordinator._async_update_data()

    assert result.latest_version is None
    assert coordinator.last_successful_check is None
    assert coordinator.last_check_error == "Invalid GitHub update metadata"
    assert "GitHub releases response is not a list" in caplog.text


async def test_unrelated_value_error_is_not_suppressed(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Programming errors outside metadata validation remain visible."""
    coordinator = MeshCoreNocUpdateCoordinator(hass, UPDATE_CHANNEL_STABLE)
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.meshcore_noc.updater._async_get_stable_update",
        AsyncMock(side_effect=ValueError("unrelated")),
    )

    with pytest.raises(ValueError, match="unrelated"):
        await coordinator._async_update_data()
