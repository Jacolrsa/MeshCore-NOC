# Changelog

All notable changes to MeshCore NOC will be documented in this file.

The format is based on Keep a Changelog, and versioning follows Semantic
Versioning.

## [1.1.0-dev]

### Added

- Backend-only `meshcore_noc.sync_repeater_clock` action for one managed
  repeater, with read-before-sync, asynchronous remote-result correlation, and
  read-after-sync verification.

### Changed

- Corrected Clock Intelligence documentation to describe the source-backed
  authenticated `clock sync` command and its forward-only behavior.

## [1.0.0] - 2026-07-28

First clean public release of MeshCore NOC.

### Added

- Automatic Mission Control dashboard for managed MeshCore repeaters.
- Stable managed-device discovery and identity mapping.
- Calibrated voltage, battery percentage, health, and freshness monitoring.
- Clock Intelligence with individual and serialized fleet clock checks.
- Clock offset, status, round-trip timing, timeout, cooldown, and diagnostics.
- Home Assistant services, entities, local branding, and update integration.
- Independent MeshCore NOC branding and complete trademark-safety audit.
- Stable and Development update channels with validated staged installation.

### Fixed

- Managed clock targets resolve through ordered registry and entity metadata,
  continuing after ambiguous evidence until a unique public-key prefix is found.
- Home Assistant clock commands use only the public
  `meshcore.execute_command` service payload.
- Dashboard rendering, lifecycle cleanup, and update handling are hardened for
  Home Assistant operation.

### Upgrade note

Development installations using a pre-release 4.x version must be removed and
installed fresh because the public release version sequence restarts at 1.0.0.
