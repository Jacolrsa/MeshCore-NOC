"""Stable and development update support for MeshCore NOC."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from aiohttp import ClientError, ClientResponseError
from awesomeversion import AwesomeVersion, AwesomeVersionException
from homeassistant.components import persistent_notification
from homeassistant.components.homeassistant.const import SERVICE_HOMEASSISTANT_RESTART
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    INTEGRATION_VERSION,
    UPDATE_CHANNEL_DEVELOPMENT,
    UPDATE_CHANNEL_STABLE,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_BRANCH = "v4-development"
REPOSITORY_URL = "https://github.com/Jacolrsa/MeshCore-NOC"
DEVELOPMENT_RELEASE_URL = f"{REPOSITORY_URL}/tree/{UPDATE_BRANCH}"
DEVELOPMENT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Jacolrsa/MeshCore-NOC/"
    f"{UPDATE_BRANCH}/custom_components/meshcore_noc/manifest.json"
)
DEVELOPMENT_CHANGELOG_URL = (
    "https://raw.githubusercontent.com/Jacolrsa/MeshCore-NOC/"
    f"{UPDATE_BRANCH}/CHANGELOG.md"
)
DEVELOPMENT_ARCHIVE_URL = f"{REPOSITORY_URL}/archive/refs/heads/{UPDATE_BRANCH}.zip"
DEVELOPMENT_COMMIT_URL = (
    f"https://api.github.com/repos/Jacolrsa/MeshCore-NOC/commits/{UPDATE_BRANCH}"
)
STABLE_RELEASES_URL = (
    "https://api.github.com/repos/Jacolrsa/MeshCore-NOC/releases?per_page=20"
)

# Compatibility aliases retained for older tests and callers.
RELEASE_URL = DEVELOPMENT_RELEASE_URL
MANIFEST_URL = DEVELOPMENT_MANIFEST_URL
CHANGELOG_URL = DEVELOPMENT_CHANGELOG_URL
ARCHIVE_URL = DEVELOPMENT_ARCHIVE_URL

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
BACKUP_LIMIT = 5
UPDATE_INTERVAL = timedelta(hours=6)
RESTART_NOTIFICATION_ID = "meshcore_noc_update_restart_required"
_PROJECT_ALPHA_VERSION = re.compile(
    r"^(?P<base>\d+\.\d+\.\d+)-alpha(?P<suffix>\d+(?:\.\d+)*)$"
)


class NoStableReleaseError(ValueError):
    """Raised when GitHub has no eligible stable release."""


class UpdateMetadataError(ValueError):
    """Raised when GitHub returns update metadata in an unexpected shape."""


REQUIRED_INTEGRATION_FILES = frozenset(
    {
        "__init__.py",
        "binary_sensor.py",
        "config_flow.py",
        "const.py",
        "coordinator.py",
        "dashboard.py",
        "diagnostics.py",
        "discovery.py",
        "entity.py",
        "frontend/meshcore-noc-dashboard.js",
        "manifest.json",
        "models.py",
        "naming.py",
        "sensor.py",
        "strings.json",
        "translations/en.json",
        "update.py",
        "updater.py",
    }
)


@dataclass(frozen=True, slots=True)
class UpdateData:
    """Latest known metadata for the selected update channel."""

    latest_version: str | None = None
    release_summary: str | None = None
    release_notes: str | None = None
    release_url: str | None = None
    archive_url: str | None = None
    source_url_type: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    commit_url: str | None = None
    commit_message: str | None = None
    commit_timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class InstallationResult:
    """Result of a staged on-disk integration replacement."""

    backup_path: Path
    installed_manifest_version: str


class MeshCoreNocUpdateCoordinator(DataUpdateCoordinator[UpdateData]):
    """Poll and install the selected MeshCore NOC update channel."""

    def __init__(
        self, hass: HomeAssistant, channel: str = UPDATE_CHANNEL_STABLE
    ) -> None:
        """Initialize update state without affecting managed repeaters."""
        if channel not in {UPDATE_CHANNEL_STABLE, UPDATE_CHANNEL_DEVELOPMENT}:
            channel = UPDATE_CHANNEL_STABLE
        self.channel = channel
        super().__init__(
            hass,
            _LOGGER,
            name=f"MeshCore NOC {channel} updates",
            update_interval=UPDATE_INTERVAL,
        )
        self.data = UpdateData(
            source_url_type=(
                "github_raw_branch"
                if channel == UPDATE_CHANNEL_DEVELOPMENT
                else "github_release_api"
            ),
            branch=UPDATE_BRANCH if channel == UPDATE_CHANNEL_DEVELOPMENT else None,
        )
        self.last_check_time = None
        self.last_successful_check = None
        self.last_check_error: str | None = None
        self.installation_state = "idle"
        self._install_lock = asyncio.Lock()

    async def _async_update_data(self) -> UpdateData:
        """Fetch and retain metadata for the selected channel."""
        self.last_check_time = dt_util.utcnow()
        try:
            session = async_get_clientsession(self.hass)
            if self.channel == UPDATE_CHANNEL_DEVELOPMENT:
                result = await _async_get_development_update(session)
            else:
                result = await _async_get_stable_update(session)
        except NoStableReleaseError as err:
            self.last_successful_check = dt_util.utcnow()
            self.last_check_error = _concise_error(err)
            return UpdateData(source_url_type="github_release_api")
        except UpdateMetadataError as err:
            self.last_check_error = _concise_error(err)
            _LOGGER.debug("MeshCore NOC update metadata is invalid: %s", err)
            return UpdateData(
                source_url_type=(
                    "github_raw_branch"
                    if self.channel == UPDATE_CHANNEL_DEVELOPMENT
                    else "github_release_api"
                ),
                branch=(
                    UPDATE_BRANCH
                    if self.channel == UPDATE_CHANNEL_DEVELOPMENT
                    else None
                ),
            )
        except (
            AwesomeVersionException,
            ClientError,
            RuntimeError,
            TimeoutError,
            TypeError,
            json.JSONDecodeError,
        ) as err:
            self.last_check_error = _concise_error(err)
            _LOGGER.warning(
                "MeshCore NOC update check failed: %s", self.last_check_error
            )
            return self.data

        self.last_successful_check = dt_util.utcnow()
        self.last_check_error = None
        return result

    async def async_install_latest(self) -> InstallationResult:
        """Download, validate, back up, and atomically install the offered version."""
        if self._install_lock.locked():
            raise HomeAssistantError("A MeshCore NOC update is already in progress")
        if self.data.latest_version is None:
            raise HomeAssistantError("No checked MeshCore NOC update is available")
        if self.data.archive_url is None:
            raise HomeAssistantError("The selected update has no install archive")
        if not version_is_newer(self.data.latest_version, INTEGRATION_VERSION):
            raise HomeAssistantError("No newer MeshCore NOC update is available")

        async with self._install_lock:
            self.installation_state = "downloading"
            try:
                archive = await _async_download_archive(
                    async_get_clientsession(self.hass), self.data.archive_url
                )
                self.installation_state = "installing"
                result = await self.hass.async_add_executor_job(
                    _install_archive,
                    Path(self.hass.config.config_dir),
                    archive,
                    self.data.latest_version,
                )
            except Exception:
                self.installation_state = "failed"
                raise

            self.installation_state = "restart_required"
            await self._async_request_restart()
            return result

    async def _async_request_restart(self) -> None:
        """Request a supported Core restart or explain that one is required."""
        message = (
            f"MeshCore NOC {self.data.latest_version} has been staged and backed up. "
            "Home Assistant must restart before the loaded integration version changes."
        )
        persistent_notification.async_create(
            self.hass,
            message,
            title="MeshCore NOC update installed",
            notification_id=RESTART_NOTIFICATION_ID,
        )
        if self.hass.services.has_service(
            "homeassistant", SERVICE_HOMEASSISTANT_RESTART
        ):
            self.installation_state = "restart_requested"
            await self.hass.services.async_call(
                "homeassistant",
                SERVICE_HOMEASSISTANT_RESTART,
                blocking=False,
            )


async def _async_get_stable_update(session: Any) -> UpdateData:
    """Return the newest valid non-draft, non-prerelease GitHub release."""
    payload = await _async_get_json_value(session, STABLE_RELEASES_URL)
    if not isinstance(payload, list):
        raise UpdateMetadataError("GitHub releases response is not a list")
    for release in payload:
        if (
            not isinstance(release, dict)
            or release.get("draft")
            or release.get("prerelease")
        ):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            continue
        version = tag.strip().removeprefix("v")
        try:
            parsed_version = AwesomeVersion(version)
        except AwesomeVersionException:
            continue
        if not parsed_version.valid:
            continue
        archive_url = release.get("zipball_url")
        release_url = release.get("html_url")
        if not isinstance(archive_url, str) or not isinstance(release_url, str):
            continue
        notes = release.get("body") if isinstance(release.get("body"), str) else None
        title = (
            release.get("name")
            if isinstance(release.get("name"), str) and release.get("name")
            else version
        )
        return UpdateData(
            latest_version=version,
            release_summary=str(title)[:255],
            release_notes=notes,
            release_url=release_url,
            archive_url=archive_url,
            source_url_type="github_release_api",
        )
    raise NoStableReleaseError("No valid stable GitHub release is available")


async def _async_get_development_update(session: Any) -> UpdateData:
    """Return branch manifest, changelog, and latest commit metadata."""
    manifest = await _async_get_json(session, DEVELOPMENT_MANIFEST_URL)
    _validate_manifest(manifest)
    latest_version = str(manifest["version"])
    try:
        changelog = await _async_get_text(session, DEVELOPMENT_CHANGELOG_URL)
        notes = _release_notes_for(changelog, latest_version)
    except (
        ClientError,
        RuntimeError,
        TimeoutError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        notes = f"Development update {latest_version}."
    try:
        commit = await _async_get_json(session, DEVELOPMENT_COMMIT_URL)
    except (
        ClientError,
        RuntimeError,
        TimeoutError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        commit = {}
    commit_data = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    author = (
        commit_data.get("author") if isinstance(commit_data.get("author"), dict) else {}
    )
    commit_sha = commit.get("sha") if isinstance(commit.get("sha"), str) else None
    commit_url = (
        commit.get("html_url") if isinstance(commit.get("html_url"), str) else None
    )
    if commit_url is None and commit_sha is not None:
        commit_url = f"{REPOSITORY_URL}/commit/{commit_sha}"
    return UpdateData(
        latest_version=latest_version,
        release_summary=_release_summary(notes, latest_version),
        release_notes=notes,
        release_url=commit_url or DEVELOPMENT_RELEASE_URL,
        archive_url=DEVELOPMENT_ARCHIVE_URL,
        source_url_type="github_raw_branch",
        branch=UPDATE_BRANCH,
        commit_sha=commit_sha,
        commit_url=commit_url,
        commit_message=(
            commit_data.get("message")
            if isinstance(commit_data.get("message"), str)
            else None
        ),
        commit_timestamp=(
            author.get("date") if isinstance(author.get("date"), str) else None
        ),
    )


async def _async_get_json(session: Any, url: str) -> dict[str, Any]:
    """Fetch one trusted HTTPS JSON document."""
    value = await _async_get_json_value(session, url)
    if not isinstance(value, dict):
        raise UpdateMetadataError("GitHub manifest is not a JSON object")
    return value


async def _async_get_json_value(session: Any, url: str) -> Any:
    """Fetch one trusted JSON value."""
    try:
        return json.loads(await _async_get_text(session, url))
    except json.JSONDecodeError as err:
        raise UpdateMetadataError("GitHub response is not valid JSON") from err


async def _async_get_text(session: Any, url: str) -> str:
    """Fetch one bounded official GitHub text resource."""
    _validate_source_url(url)
    async with session.get(url, timeout=30) as response:
        _validate_response_url(str(response.url))
        response.raise_for_status()
        return await response.text()


async def _async_download_archive(session: Any, url: str) -> bytes:
    """Download the official archive with a compressed-size limit."""
    _validate_source_url(url)
    chunks: list[bytes] = []
    size = 0
    async with session.get(url, timeout=60) as response:
        _validate_response_url(str(response.url))
        response.raise_for_status()
        async for chunk in response.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise HomeAssistantError("MeshCore NOC update archive is too large")
            chunks.append(chunk)
    return b"".join(chunks)


def _validate_source_url(url: str) -> None:
    """Allow only MeshCore NOC endpoints on official GitHub hosts."""
    parsed = urlparse(url)
    allowed = parsed.scheme == "https" and (
        (
            parsed.hostname == "raw.githubusercontent.com"
            and parsed.path.startswith("/Jacolrsa/MeshCore-NOC/")
        )
        or (
            parsed.hostname == "api.github.com"
            and parsed.path.startswith("/repos/Jacolrsa/MeshCore-NOC/")
        )
        or (
            parsed.hostname == "github.com"
            and parsed.path.startswith("/Jacolrsa/MeshCore-NOC/")
        )
    )
    if not allowed:
        raise ValueError("Untrusted MeshCore NOC update URL")


def _validate_response_url(url: str) -> None:
    """Reject redirects outside GitHub's official HTTPS download hosts."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "api.github.com",
        "github.com",
        "raw.githubusercontent.com",
        "codeload.github.com",
    }:
        raise UpdateMetadataError(
            "GitHub redirected the update request to an unsafe host"
        )


def _validate_manifest(
    manifest: dict[str, Any], offered_version: str | None = None
) -> None:
    """Validate domain and version before trusting update content."""
    if manifest.get("domain") != DOMAIN:
        raise UpdateMetadataError("Update manifest has the wrong domain")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise UpdateMetadataError("Update manifest has no valid version")
    parsed_version = AwesomeVersion(version)
    if not parsed_version.valid:
        raise UpdateMetadataError("Update manifest has no valid version")
    if offered_version is not None and version != offered_version:
        raise UpdateMetadataError(
            "Archive version does not match the offered version"
        )


def version_is_newer(latest_version: str, installed_version: str) -> bool:
    """Compare versions with AwesomeVersion and the project's alpha iteration."""
    if latest_version == installed_version:
        return False

    latest_match = _PROJECT_ALPHA_VERSION.fullmatch(latest_version)
    installed_match = _PROJECT_ALPHA_VERSION.fullmatch(installed_version)
    if latest_match is not None and installed_match is not None:
        latest_base = AwesomeVersion(latest_match["base"])
        installed_base = AwesomeVersion(installed_match["base"])
        if latest_base != installed_base:
            return latest_base > installed_base
        latest_suffix = tuple(int(part) for part in latest_match["suffix"].split("."))
        installed_suffix = tuple(
            int(part) for part in installed_match["suffix"].split(".")
        )
        return latest_suffix > installed_suffix

    try:
        latest = AwesomeVersion(latest_version)
        installed = AwesomeVersion(installed_version)
    except AwesomeVersionException:
        return False
    if not latest.valid or not installed.valid:
        return False
    return latest > installed


def _install_archive(
    config_dir: Path,
    archive: bytes,
    offered_version: str,
) -> InstallationResult:
    """Synchronously stage and atomically replace the integration with rollback."""
    custom_components = config_dir / "custom_components"
    installed = custom_components / DOMAIN
    backups = config_dir / "meshcore_noc_backups"
    custom_components.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".meshcore_noc_update-", dir=config_dir
    ) as working_name:
        working = Path(working_name)
        staged = working / "staged"
        source = _extract_validated_component(archive, staged, offered_version)
        candidate = custom_components / f".{DOMAIN}-new-{uuid4().hex}"
        previous = custom_components / f".{DOMAIN}-old-{uuid4().hex}"
        backup = _create_backup(installed, backups, INTEGRATION_VERSION)
        moved_old = False
        try:
            shutil.copytree(source, candidate)
            _validate_installed_tree(candidate, offered_version)
            os.replace(installed, previous)
            moved_old = True
            os.replace(candidate, installed)
            _validate_installed_tree(installed, offered_version)
        except Exception:
            if moved_old:
                if installed.exists():
                    shutil.rmtree(installed)
                os.replace(previous, installed)
            if candidate.exists():
                shutil.rmtree(candidate)
            raise
        else:
            shutil.rmtree(previous)
            _prune_backups(backups)

    return InstallationResult(backup, offered_version)


def _extract_validated_component(
    archive: bytes,
    destination: Path,
    offered_version: str,
) -> Path:
    """Validate every ZIP member and extract only the integration subtree."""
    try:
        zip_file = zipfile.ZipFile(BytesIO(archive))
    except zipfile.BadZipFile as err:
        raise ValueError("Downloaded update is not a valid ZIP archive") from err

    with zip_file:
        infos = zip_file.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("Update archive contains too many files")
        total_size = 0
        manifest_members: list[str] = []
        for info in infos:
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or info.flag_bits & 0x1
            ):
                raise ValueError("Update archive contains an unsafe path")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("Update archive contains a symbolic link")
            total_size += info.file_size
            if total_size > MAX_EXTRACTED_BYTES:
                raise ValueError("Expanded update archive is too large")
            if info.filename.endswith("custom_components/meshcore_noc/manifest.json"):
                manifest_members.append(info.filename)
        if len(manifest_members) != 1:
            raise ValueError("Update archive has no unique MeshCore NOC manifest")

        component_prefix = manifest_members[0].removesuffix("manifest.json")
        destination.mkdir(parents=True)
        for info in infos:
            if info.is_dir() or not info.filename.startswith(component_prefix):
                continue
            relative = PurePosixPath(info.filename.removeprefix(component_prefix))
            if not relative.parts:
                continue
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info) as source_file, target.open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)

    _validate_installed_tree(destination, offered_version)
    return destination


def _validate_installed_tree(path: Path, offered_version: str) -> None:
    """Verify required files and manifest identity in a staged tree."""
    missing = sorted(
        relative
        for relative in REQUIRED_INTEGRATION_FILES
        if not (path / relative).is_file()
    )
    if missing:
        raise ValueError(f"Update is missing required integration file: {missing[0]}")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    _validate_manifest(manifest, offered_version)


def _create_backup(installed: Path, backups: Path, version: str) -> Path:
    """Create a timestamped integration-only backup."""
    if not installed.is_dir():
        raise FileNotFoundError("Installed MeshCore NOC directory was not found")
    timestamp = dt_util.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_version = "".join(char for char in version if char.isalnum() or char in ".-_")
    target = backups / f"{timestamp}-{safe_version}"
    suffix = 1
    while target.exists():
        target = backups / f"{timestamp}-{safe_version}-{suffix}"
        suffix += 1
    shutil.copytree(installed, target)
    return target


def _prune_backups(backups: Path) -> None:
    """Keep only the five newest integration backups."""
    entries = sorted(
        (path for path in backups.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for stale in entries[BACKUP_LIMIT:]:
        shutil.rmtree(stale)


def _release_notes_for(changelog: str, version: str) -> str:
    """Return only the changelog section for the offered version."""
    marker = f"## [{version}]"
    start = changelog.find(marker)
    if start < 0:
        return f"Development update {version}."
    next_section = changelog.find("\n## [", start + len(marker))
    return changelog[start : next_section if next_section >= 0 else None].strip()


def _release_summary(notes: str, version: str) -> str:
    """Return a short Home Assistant update summary."""
    for line in notes.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:255]
    return f"MeshCore NOC development update {version}"[:255]


def _concise_error(err: Exception) -> str:
    """Return a redacted error suitable for diagnostics."""
    if isinstance(err, ClientResponseError):
        return f"GitHub returned HTTP {err.status}"
    if isinstance(err, NoStableReleaseError):
        return "No stable release available"
    if isinstance(err, UpdateMetadataError):
        return "Invalid GitHub update metadata"
    return type(err).__name__
