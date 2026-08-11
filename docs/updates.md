# MeshCore NOC update channels

The MeshCore NOC controller device provides one native Home Assistant Update
entity. Select its source under **Settings → Devices & services → MeshCore NOC
→ Configure → Update channel**.

## Stable

Stable is the default and recommended channel. It reads GitHub Releases for
`Jacolrsa/MeshCore-NOC`, ignores drafts and prereleases, and offers the newest
valid published production version.

For 1.1.0 the release manifest and backend version constant are both `1.1.0`.
The Stable channel will not offer a beta/prerelease as a production update.

To publish a stable update:

1. Set the same production version in
   `custom_components/meshcore_noc/manifest.json` and `const.py`.
2. Run the repository validation suite.
3. Merge the release branch to `main` without discarding any main-only commits.
4. Create a matching Git tag.
5. Publish a non-draft, non-prerelease GitHub Release for that tag.
6. Include release notes and upgrade/rollback guidance.

## Development

Development follows the active `v1.1-clock-sync` branch for the current 1.1
maintenance cycle. It reports the branch manifest version and latest commit
metadata when GitHub provides them.

Development may contain unfinished work. Detection is version-based: a commit
with an unchanged manifest version is not offered as a normal Home Assistant
update, so development builds intended for field installation must use a unique
manifest version.

## Installation safeguards

The integration checks for updates at startup and at most every six hours unless
Home Assistant requests an explicit refresh.

Installation validates:

- archive path safety;
- symlink handling;
- archive and extracted size limits;
- required integration files;
- manifest domain; and
- exact requested version.

Before replacement, the updater creates an integration-only backup under
`/config/meshcore_noc_backups` and keeps a bounded number of recent backups.
The loaded integration version changes only after a Home Assistant restart.

## HACS custom-repository installs

When the repository is installed through HACS as a custom integration, a release
can also be selected with **HACS → MeshCore NOC → Redownload**. Perform a full
Home Assistant restart after redownload so both Python modules and the frontend
cache-busting version are refreshed.

## Rollback

If a new release fails before or during updater replacement, the staged updater
attempts to restore the previous integration directory. For manual/HACS
rollback, select the previous known-good release, redownload/copy it, and restart
Home Assistant.

Do not remove and re-add the MeshCore NOC config entry as a normal rollback
step; keeping the entry preserves managed stable IDs and per-repeater settings.
