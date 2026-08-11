"""Compatibility entry point for the current MeshCore NOC clock workflow."""

from . import updater as _updater
from .epoch_sync_beta15 import install_epoch_sync as _install_beta15


def _align_development_update_channel() -> None:
    """Point the Development updater at the active v1.1 beta branch."""
    branch = "v1.1-clock-sync"
    repository_url = "https://github.com/Jacolrsa/MeshCore-NOC"
    _updater.UPDATE_BRANCH = branch
    _updater.DEVELOPMENT_RELEASE_URL = f"{repository_url}/tree/{branch}"
    _updater.DEVELOPMENT_MANIFEST_URL = (
        f"https://raw.githubusercontent.com/Jacolrsa/MeshCore-NOC/{branch}/"
        "custom_components/meshcore_noc/manifest.json"
    )
    _updater.DEVELOPMENT_CHANGELOG_URL = (
        f"https://raw.githubusercontent.com/Jacolrsa/MeshCore-NOC/{branch}/CHANGELOG.md"
    )
    _updater.DEVELOPMENT_ARCHIVE_URL = (
        f"{repository_url}/archive/refs/heads/{branch}.zip"
    )
    _updater.DEVELOPMENT_COMMIT_URL = (
        f"https://api.github.com/repos/Jacolrsa/MeshCore-NOC/commits/{branch}"
    )
    _updater.RELEASE_URL = _updater.DEVELOPMENT_RELEASE_URL
    _updater.MANIFEST_URL = _updater.DEVELOPMENT_MANIFEST_URL
    _updater.CHANGELOG_URL = _updater.DEVELOPMENT_CHANGELOG_URL
    _updater.ARCHIVE_URL = _updater.DEVELOPMENT_ARCHIVE_URL


def install_epoch_sync() -> None:
    """Install beta15 and align the development update source."""
    _align_development_update_channel()
    _install_beta15()


__all__ = ("install_epoch_sync",)
