# MeshCore NOC update channels

The MeshCore NOC controller device provides one native Home Assistant Update
entity. Select its source under **Settings → Devices & services → MeshCore NOC
→ Configure → Update channel**.

## Stable

Stable is the default and recommended channel. It reads GitHub Releases for
`Jacolrsa/MeshCore-NOC`, ignores drafts and prereleases, and offers the newest
valid published production version. Release title, notes, page URL, and archive
are used by the native Update entity.

To publish a stable update:

1. Set the release version in
   `custom_components/meshcore_noc/manifest.json` and the backend version
   constant.
2. Create a matching Git tag.
3. Publish a non-draft, non-prerelease GitHub Release for that tag.
4. Include useful release notes.

## Development

Development reads
`custom_components/meshcore_noc/manifest.json` from `v4-development`. It also
reports the latest branch commit SHA, page, message, and timestamp when GitHub
provides them. This channel is intended for maintainers and testers and may
contain unfinished or unstable work.

Development detection is version-based. A new commit with an unchanged
manifest version is not a normal Home Assistant update. Increment the manifest
version when a development build must be offered.

## Checking and installation

The integration checks at startup and every six hours. Home Assistant's entity
refresh action can request an immediate check. A temporary failure retains the
last successful remote result; if no check has ever succeeded, the latest
version and entity state remain unknown.

Installation downloads the archive for the selected channel, validates ZIP
paths, symlinks, size, required integration files, manifest domain, and exact
version, and stages only `custom_components/meshcore_noc`. It creates an
integration-only backup before atomic replacement and restores the previous
directory if replacement validation fails. A successful installation requires
a Home Assistant Core restart before the loaded version changes.
