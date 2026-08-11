# Changelog

All notable changes to MeshCore NOC will be documented in this file.

The format is based on Keep a Changelog, and versioning follows Semantic
Versioning.

## [1.1.0-beta7]

### Added

- Authenticated repeater clock synchronisation that uses the Home Assistant UTC
  system clock instead of copying the connected MeshCore companion clock.
- Safe operator-visible clock-sync activity lines on each repeater detail page.
- Explicit repeater-password requirement and clearer password save failures.

### Changed

- Clock synchronisation now logs in to the repeater, sends `clkreboot`, waits
  10 seconds for reboot, logs in again, sends `time <epoch_seconds>` from Home
  Assistant UTC, waits another 10 seconds, and performs a final `clock` check.
- The Repeater access section is displayed immediately beside the repeater clock
  workflow so credentials are configured before an authenticated operation.
- Any remote response received while setting time is retained in the operator
  sync transcript without exposing the stored password.

### Security

- Repeater passwords remain private backend-only values and are never included
  in entities, diagnostics, command transcripts, or logs.

## [1.1.0-beta6]

### Fixed

- Allowed the dashboard's single-repeater clock-sync action to call the Home
  Assistant service without explicitly requesting a structured response.

## [1.1.0-beta5]

### Added

- Persistent per-repeater management settings keyed by the existing NOC stable
  ID, including battery calibration, monitoring thresholds, display name, and
  a private repeater password record.
- Administrator-only dashboard management API that never returns or logs
  stored passwords.
- Editable repeater detail sections with explicit Save, Cancel, and Reset
  Defaults controls, live battery-calibration preview, validation feedback,
  and previous/next repeater navigation.

### Changed

- Polished the beta4 fleet layout with calmer network status, consistent
  health colours, clock offsets, and operator-facing `Last Seen` wording.
- Applied per-repeater calibration, battery/freshness thresholds, and clock
  warning/critical thresholds without changing entity IDs or service names.
- Preserved missing recorder history as gaps instead of interpreting absent
  values as zero volts.

### Security

- Repeater passwords are stored in Home Assistant private persistent storage,
  never exposed through entities, websocket reads, logs, or diagnostics, and
  can only be changed or removed by an administrator.

## [1.1.0-beta4]

### Changed

- Reworked Mission Control into a compact Network Operations Centre layout
  with combined status, alerts, and fleet clock controls.
- Replaced oversized repeater cards with a concise, navigable fleet list and
  dedicated per-repeater detail subviews.
- Made the bundled recorder-backed fleet voltage chart the main visual focus,
  with 24-hour, 7-day, and 30-day ranges and safe invalid-value filtering.
- Consolidated monitoring, single-repeater clock actions, identity,
  calibration values, configuration guidance, and diagnostics in each detail
  view.

### Preserved

- Existing entity identities, service names and schemas, managed discovery,
  clock execution, automatic scheduling, diagnostics, and unload/reload
  behaviour.

## [1.1.0-beta3]

### Added

- Central fleet Clock Management with sequential all-repeater clock checks and
  synchronisation, structured per-repeater results, progress, and safe
  cross-operation concurrency protection.
- Optional integration-managed automatic fleet clock synchronisation at 6, 12,
  24, 72, or 168 hour intervals, disabled by default, with persisted schedule
  and last-run state.
- Dashboard fleet sync controls, companion-clock safety warning, readable
  offsets, and compact managed-repeater results.

## [1.1.0-beta2]

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
