<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="branding/banner/github_banner_dark.png">
    <source media="(prefers-color-scheme: light)" srcset="branding/banner/github_banner_light.png">
    <img src="branding/banner/github_banner_dark.png" alt="MeshCore NOC — Network Operations Centre for MeshCore" width="100%">
  </picture>

  # MeshCore NOC

  **Network Operations Centre for MeshCore**

  **Monitor • Analyse • Operate**

  _Independent Community Project_

  [![Version](https://img.shields.io/badge/version-1.1.0-4da3ff)](CHANGELOG.md)
  [![Status](https://img.shields.io/badge/status-stable-36c96b)](ROADMAP.md)
  [![Home Assistant](https://img.shields.io/badge/Home%20Assistant-custom%20integration-41bdf5)](https://www.home-assistant.io/)
  [![Branch](https://img.shields.io/badge/branch-main-4da3ff)](https://github.com/Jacolrsa/MeshCore-NOC/tree/main)
</div>

## What MeshCore NOC does

MeshCore NOC turns MeshCore telemetry and repeater identity into a focused Home
Assistant operations interface. It discovers upstream MeshCore devices, lets an
operator select a managed fleet, creates stable NOC entities, and provides a
Mission Control dashboard for day-to-day monitoring and clock management.

MeshCore remains responsible for radio transport, contacts, routing and raw
telemetry. MeshCore NOC uses supported Home Assistant state, registry, service
and event contracts and does not replace the upstream MeshCore integration.

## v1.1.0 highlights

### Mission Control

- Responsive fleet overview with network health, alerts and fleet actions.
- Fleet rows use the worst current condition from availability/health, battery
  and clock state so warning, degraded and critical repeaters are immediately
  visible.
- Per-repeater detail pages provide monitoring, clock controls, calibration,
  thresholds, identity/display settings and private administrator-password
  management.
- Recorder-backed fleet voltage history now refreshes in the background without
  blanking the graph, includes a 6 h range, time-axis labels, current values,
  period change, clickable series visibility and an interactive crosshair.
- Recorder gaps remain gaps. Large instantaneous calibration/recorder jumps are
  broken visually instead of being drawn as misleading vertical voltage events.

### Clock Intelligence

- **Check Clock requires the saved repeater administrator password.**
- Login and clock-command waits use MeshCore's route-provided
  `suggested_timeout` rather than one fixed timeout for direct and multi-hop
  repeaters.
- Measured clock-command RTT is used to compensate radio travel time when
  calculating displayed repeater clock offset.
- Clock synchronisation uses Home Assistant UTC as the authoritative source and
  compensates the outgoing timestamp with the measured one-way route estimate.
- Repeaters already within ±30 seconds are left untouched: no reboot and no
  clock write are performed.
- Companion clock recovery can repair future contact `lastmod` timestamps,
  persist them safely, reboot the companion and then move its clock forward to
  Home Assistant UTC without deleting contacts or factory-resetting the device.
- Anti-replay recovery handles repeaters that retained an old future
  administrator timestamp after the companion clock was corrected.

### Automation

- Serialized **Check All** and **Sync All** operations never intentionally run
  multiple repeater clock transactions in parallel.
- Automatic fleet clock checks can run at a configured interval.
- Automatic clock synchronisation is disabled by default and supports 6, 12,
  24, 72 or 168 hour intervals.
- Unattended automatic synchronisation will not start if a managed repeater is
  missing its saved administrator password.
- Legacy manual-check cooldown and fleet success/failure pacing controls are no
  longer exposed in the v1.1 options UI.

Read the [v1.1 release notes](docs/V1_1_RELEASE.md) for the complete operational
sequence and validation notes.

## Managed entities

Each selected managed repeater has NOC-owned entities for:

- calibrated voltage;
- calibrated battery percentage;
- health;
- freshness;
- clock offset;
- clock status; and
- Check Clock action.

Fleet-level entities expose check/sync state, progress, last-run results and
fleet clock health. Stable IDs remain authoritative across reloads and selection
changes.

## Health and freshness defaults

| Freshness | Condition |
| --- | --- |
| Fresh | Under 75 minutes |
| Aging | 75–119 minutes |
| Stale | 120–179 minutes |
| Offline | 180 minutes or more, or source unavailable |

Default battery thresholds are 40% warning and 20% critical. These values, the
voltage calibration, freshness thresholds, display name and clock thresholds can
be adjusted per managed repeater from its Mission Control detail page.

## Requirements

- Home Assistant with the upstream MeshCore integration configured.
- MeshCore devices represented in Home Assistant's device/entity registries.
- Home Assistant Recorder for historical graphs. Current telemetry works without
  Recorder.
- Home Assistant 2026.3 or newer for local custom-integration branding.
- A saved repeater administrator password for authenticated clock checks and
  synchronisation.

## Installation and upgrades

### HACS custom repository

If this repository is already installed as a HACS custom integration, use
**HACS → MeshCore NOC → Redownload** to install a selected release, then perform
a full Home Assistant restart.

### Manual installation

1. Back up Home Assistant.
2. Download the stable release or check out `main`.
3. Copy `custom_components/meshcore_noc` to
   `/config/custom_components/meshcore_noc`.
4. Confirm `/config/custom_components/meshcore_noc/manifest.json` exists.
5. Restart Home Assistant fully.
6. Add or reload **MeshCore NOC** under **Settings → Devices & services**.

Do not remove and re-add a working MeshCore NOC config entry during a normal
upgrade. Replace/redownload the component and restart Home Assistant so registry
identities and retained settings stay attached to the same stable IDs.

See [Installation](docs/installation.md) and
[Troubleshooting](docs/troubleshooting.md).

## Configuration

Open **Settings → Devices & services → MeshCore NOC → Configure**.

The v1.1 options page intentionally contains only active operator controls:

- managed MeshCore devices;
- update channel;
- automatic fleet clock checks and interval; and
- automatic clock synchronisation and interval.

Per-repeater calibration, monitoring thresholds, display name and administrator
password live on the repeater detail page in Mission Control.

## Clock-check workflow

A normal authenticated check is:

```text
Home Assistant UTC
      ↓
password login to repeater
      ↓ route-provided suggested_timeout
login confirmation
      ↓ short radio settle
clock command
      ↓ route-provided suggested_timeout
clock reply + measured RTT
      ↓
latency-compensated offset/status
```

Direct repeaters normally complete much faster than routed repeaters. NOC waits
for the timeout returned by the actual MeshCore transmission instead of applying
the same fixed window to every route.

## Clock-sync workflow

NOC first performs the same authenticated, latency-aware pre-check. If the
repeater is already within ±30 seconds, it reports success without changing the
repeater.

When correction is required, NOC performs the anti-replay-safe reboot/login
sequence, verifies the connected companion clock, repairs an ahead-running
companion only when required, sends a latency-compensated clock sync timestamp,
and performs a final authenticated verification. A sync is successful only when
the verified final offset is inside the ±30 second window.

## Mission Control graph

The graph uses Home Assistant Recorder history and remains self-contained; no
ApexCharts or external frontend card is required.

- 6 h / 24 h / 7 d / 30 d ranges.
- Background refresh keeps the last good graph visible while new Recorder data
  is fetched.
- A temporary Recorder/API refresh failure keeps the last good graph visible and
  reports the refresh problem instead of clearing the panel.
- The x-axis shows time/date context and the legend shows current voltage and
  change over the selected period.
- Click a legend item to hide/show a repeater series.
- Move over the plot for a crosshair and timestamped per-repeater values.

## Update channels

**Stable** is the default. It reads published, non-prerelease GitHub Releases.

**Development** follows the active `v1.1-clock-sync` development branch and may
contain unfinished work. Detection is version-based, so a development build
must change the manifest version before Home Assistant offers it as an update.

Both channels use the native MeshCore NOC Update entity. Update installation
validates the archive and integration manifest, creates an integration-only
backup, stages replacement, and requires a Home Assistant restart before the
loaded version changes. See [Update channels](docs/updates.md).

## Diagnostics and security

Download diagnostics from **Settings → Devices & services → MeshCore NOC →
three-dot menu → Download diagnostics**.

Repeater administrator passwords are stored in Home Assistant private storage.
They are not returned by the management API, exposed in entities/diagnostics, or
written to normal integration logs.

Before sharing diagnostics, redact private node IDs, locations and any other
sensitive context.

## Documentation

| Document | Purpose |
| --- | --- |
| [v1.1 release notes](docs/V1_1_RELEASE.md) | Final v1.1 behaviour, clock workflow, automation and graph changes |
| [MH-100 — UI Specification](docs/MH-100_UI_Specification.md) | Mission Control requirements and acceptance criteria |
| [MH-101 — Design System](docs/MH-101_Design_System.md) | Visual semantics and accessibility |
| [MH-103 — Architecture](docs/MH-103_Architecture.md) | Integration ownership and data flow |
| [MH-104 — Release Process](docs/MH-104_Release_Process.md) | Release validation and rollback |
| [Installation](docs/installation.md) | Deployment and live verification |
| [Update channels](docs/updates.md) | Stable/development update behaviour |
| [Troubleshooting](docs/troubleshooting.md) | Common installation, graph and clock issues |
| [Roadmap](ROADMAP.md) | Released and planned work |
| [Security](SECURITY.md) | Security reporting |

## Development checks

```sh
python scripts/validate_branding.py
python -m compileall -q custom_components/meshcore_noc
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
pytest -q
node --test tests/frontend/test_dashboard.js
git diff --check
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.

## Disclaimer

> MeshCore NOC is an independent community-developed project for use with MeshCore
> networks. It is not affiliated with, endorsed by, sponsored by, or maintained by
> the MeshCore project or its developers. MeshCore is referenced solely to describe
> compatibility.

## Licence and acknowledgements

MeshCore NOC is licensed under the MIT License. See [`LICENSE`](LICENSE).
Referenced upstream projects remain subject to their own licences.
