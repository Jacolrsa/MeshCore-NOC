# Changelog

All notable changes to MeshCore NOC are documented here. The format follows
Keep a Changelog and the project uses Semantic Versioning.

## [1.1.0] - 2026-08-11

### Added

- Password-authenticated per-repeater and fleet clock checks from Mission
  Control.
- Per-repeater private administrator-password storage behind Home Assistant's
  administrator-only management API.
- Authenticated single-repeater and fleet clock synchronisation using Home
  Assistant UTC as the authoritative time source.
- Automatic fleet clock checks and optional automatic fleet synchronisation.
- Companion-clock recovery for ahead-running companion nodes whose future
  contact `lastmod` values would otherwise reseed the wrong RTC after reboot.
- Anti-replay recovery for repeaters stranded by an earlier future companion
  timestamp.
- Route-aware login/command waits based on MeshCore `suggested_timeout` rather
  than a fixed timeout for every repeater.
- Measured clock-command RTT and latency-compensated clock offset calculation.
- Latency-compensated outbound clock-sync timestamp for routed repeaters.
- Per-repeater display name, voltage calibration, battery thresholds, freshness
  thresholds and clock thresholds in Mission Control.
- Fleet severity colouring that uses the worst current availability/health,
  battery and clock condition.
- Interactive Recorder-backed voltage graph with 6 h, 24 h, 7 d and 30 d
  ranges, x-axis time labels, current values, period change, series hide/show
  controls and crosshair values.

### Changed

- Clock Check now requires the saved repeater administrator password; anonymous
  clock reads are no longer the normal operator check path.
- Direct and multi-hop repeaters use the timing window returned by the actual
  MeshCore transmission, preventing routed nodes from being declared timed out
  while a valid response is still in flight.
- Clock synchronisation performs an authenticated, latency-aware pre-check and
  leaves repeaters inside ±30 seconds untouched; no reboot or clock write is
  performed for an already-synchronised repeater.
- Automatic clock synchronisation refuses to start unattended if any managed
  repeater is missing its saved administrator password.
- Obsolete manual clock-check cooldown, success-delay, failure-delay and
  rotating-start controls are no longer exposed in the v1.1 options UI.
- The Mission Control graph refreshes Recorder history in the background and
  keeps the last good plot visible while data is loading.
- A temporary history refresh error now retains the last good graph instead of
  replacing it with an empty/loading state.
- Large instantaneous recorder/calibration jumps are rendered as a visual break
  instead of a misleading vertical voltage event.
- Development update metadata is aligned with the active `v1.1-clock-sync`
  branch while Stable continues to consume non-prerelease GitHub Releases.

### Fixed

- Companion clocks that could not move backwards through normal `set_time` can
  be repaired remotely without deleting contacts or factory-resetting the
  companion.
- Repeater CLI replay protection no longer strands clock operations after an
  ahead-running companion has been corrected.
- Routed repeater checks no longer rely on an 8-second fixed response window.
- Radio travel time is no longer reported entirely as repeater RTC drift.
- Fleet status bars, dots and repeater names now use warning/degraded/critical
  colours instead of being overridden by a generic white foreground rule.
- Repeated Home Assistant state updates no longer make the graph visibly die and
  reload when its one-minute Recorder refresh starts.

### Security

- Repeater passwords remain backend-only private values. They are not returned
  by reads, exposed through entities or diagnostics, or included in normal
  command transcripts/logs.
- Automatic sync requires credentials for every target before an unattended run
  is allowed to start.

## [1.1.0-beta8]

### Fixed

- Updated administrator-only management WebSocket endpoints to use Home
  Assistant's supported `@websocket_api.require_admin` authorization flow,
  fixing password save/load failures on current Home Assistant releases.
- Ensured the MeshCore raw-event callback runs on Home Assistant's event loop so
  a valid repeater `clock` reply completes the pending request immediately
  instead of being recorded once as successful and later again as a timeout.
- Prevented the repeater detail page from treating the initial post-restart
  `queued` clock state as a real operation, so individual Check and Sync actions
  are available without first running Check All.

### Changed

- Fleet clock checks are response-driven and no longer add the legacy 15/30
  second inter-repeater pauses after a terminal result.
- Clock synchronisation keeps `clkreboot` as the required no-reply reset step,
  then probes for LOGIN_SUCCESS and continues as soon as the repeater is back.
- `time <epoch_seconds>` now uses Home Assistant UTC and waits only briefly for
  an optional firmware reply before immediately verifying with `clock`.
- Repeater password input is visible while being entered, then cleared after a
  successful save; saved passwords remain backend-only and are not returned to
  the browser.
- Password saving stores the value only. Password correctness is checked later
  when an administrator operation actually authenticates to the repeater.
- The repeater clock panel keeps an operator-visible activity transcript for the
  response-driven synchronisation sequence.

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
