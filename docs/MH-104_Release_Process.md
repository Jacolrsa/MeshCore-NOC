# MH-104 — MeshCore NOC Release Process

| Field | Value |
| --- | --- |
| Status | Maintainer process |
| Revision | 1.0 |
| Applies to | Stable and Development releases |

> [!WARNING]
> Never publish a release before verifying that the Home Assistant update
> entity correctly reports:
>
> - Installed version
> - Latest version
> - Release notes
> - Selected update channel

## Branch roles

- `main` is the stable v4 release line.
- `v4-development` is the active v4 development line.
- `v3-battery-intelligence` is the separate v3 production and maintenance
  line. Do not modify it as part of a v4 release.
- Stable releases are merged into `main` only after explicit review and
  complete release validation.

Feature branches may be based on the appropriate maintained line. Keep commits
small, scoped, and reviewable.

## Version sources

The loaded integration version is present in both:

- `custom_components/meshcore_noc/manifest.json`; and
- `INTEGRATION_VERSION` in `custom_components/meshcore_noc/const.py`.

They must match. The dashboard resource cache key, diagnostics, and Update
entity use the backend constant; Home Assistant integration metadata uses the
manifest.

## Development alpha release

1. Confirm the intended work belongs on `v4-development`.
2. Pull or fetch and verify local HEAD matches the expected remote base.
3. Confirm the working tree contains only reviewed release changes.
4. Choose the next alpha version.
5. Update the manifest and `INTEGRATION_VERSION` to the exact same value.
6. Add a dated section to `CHANGELOG.md` describing user-visible changes,
   compatibility, fixes, and known limitations.
7. Update documentation affected by the change.
8. Run the validation suite below.
9. Install the exact component tree in a Home Assistant validation environment.
10. Restart Home Assistant Core and verify the loaded version.
11. Verify both update channels and diagnostics.
12. Commit and push only after review.

Development update detection is version-based. A new commit with the same
manifest version is not offered as a newer build.

## Stable release

A stable release requires all alpha steps plus:

1. satisfy the version 1.0/stable readiness criteria in the roadmap;
2. remove alpha-only warnings that no longer apply;
3. complete upgrade and rollback testing from the supported prior version;
4. validate installation on the documented Home Assistant baseline;
5. prepare complete release notes;
6. create a Git tag matching the manifest version;
7. create a non-draft, non-prerelease GitHub Release for that tag; and
8. verify the Stable update channel sees the published release and ignores
   drafts and prereleases.

Do not create a GitHub Release merely to expose a development build. The
Development channel reads `v4-development` directly.

## Validation suite

Run from the repository root in a supported development environment:

```sh
python scripts/validate_branding.py
python -m compileall -q custom_components/meshcore_noc
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
pytest -q
git diff --check
```

Also run the frontend test directly when Node.js is available:

```sh
node --test tests/frontend/test_dashboard.js
```

There is no repository-level dependency lock or task runner at the Alpha5.2
baseline. Use a test environment whose Home Assistant and
`pytest-homeassistant-custom-component` versions are compatible with the
integration’s imports.

If YAML files are changed, parse them with a real YAML parser and validate any
Home Assistant configuration in a safe test instance. Do not treat text
inspection as YAML validation.

## Pre-publish checks

- [ ] Correct branch and expected base commit.
- [ ] Manifest and `INTEGRATION_VERSION` match.
- [ ] Changelog entry exists and is accurate.
- [ ] No unsupported feature is advertised.
- [ ] Python tests pass.
- [ ] Frontend tests pass.
- [ ] Ruff check and format check pass.
- [ ] Branding validation passes.
- [ ] YAML validation passes where applicable.
- [ ] `git diff --check` passes.
- [ ] Working tree is clean after the release commit.
- [ ] No credentials, node IDs, or unredacted diagnostics are included.
- [ ] Stable entity IDs and device identifiers are preserved or migrated
      explicitly.

## Home Assistant updater acceptance

Test with the files that will be published:

1. Install or upgrade the component.
2. Restart Home Assistant Core.
3. Confirm the Integration page and diagnostics show the loaded version.
4. On Stable, confirm drafts and prereleases are ignored.
5. On Development, confirm branch version and commit metadata are correct.
6. Confirm the Update entity reports installed version, latest version, release
   notes, and selected channel.
7. Trigger an entity refresh and confirm the check succeeds.
8. Test malformed or unavailable remote metadata: the entity must remain
   Unknown or retain its last successful result as designed.
9. For an offered update, verify download, backup, staged validation,
   replacement, notification, and restart.
10. After restart, confirm the new loaded version and all managed entities.

## Rollback

The native updater stores integration-only backups under:

```text
/config/meshcore_noc_backups/<timestamp>-<version>
```

If Home Assistant cannot load after an update:

1. stop Home Assistant Core;
2. move the failed `/config/custom_components/meshcore_noc` aside;
3. copy the newest known-good backup to that exact component path;
4. start Home Assistant Core;
5. verify the Integration page, diagnostics, managed devices, and logs; and
6. document the failed version and evidence before retrying.

Backups do not include `.storage`, dashboards, packages, helpers, or the
upstream MeshCore integration.

## Release acceptance checklist

- [ ] Scope approved.
- [ ] Version sources match.
- [ ] Changelog and public documentation updated.
- [ ] Automated validation passed.
- [ ] Live Home Assistant upgrade passed.
- [ ] Existing config entry preserved.
- [ ] Managed devices and four entities per selected device present.
- [ ] Calibration, freshness, and health values verified.
- [ ] Dashboard loads without errors.
- [ ] Diagnostics download works.
- [ ] Update entity reports all four required update fields.
- [ ] Rollback procedure verified or rehearsed.
- [ ] Git tag and GitHub Release metadata match, for Stable only.
- [ ] Remote branch and published artifacts point to the reviewed commit.
