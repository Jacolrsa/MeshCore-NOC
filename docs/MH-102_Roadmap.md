# MH-102 — MeshCore NOC Product Roadmap

| Field | Value |
| --- | --- |
| Status | Public roadmap |
| Revision | 1.0 |
| Current stable baseline | `4.0.0` |

This roadmap communicates direction, not a delivery commitment. Features under
“planned” are not part of the current product. No dates are assigned.

## Phase A — Foundation

**Status: substantially complete**

Implemented capabilities:

- registry-based MeshCore source discovery and selection;
- stable source identities and repeater/client classification;
- one managed MeshCore NOC device for every selected, resolved source device;
- calibrated voltage using the current fixed offset;
- calibrated battery percentage using the current fixed voltage range;
- health classification;
- telemetry freshness and offline ageing;
- stable unique IDs, including compatibility for the original ProMicro
  Repeater entities;
- source-state listeners plus a one-minute freshness timer;
- selection lifecycle reconciliation and safe cleanup of NOC-owned records;
- redacted diagnostics;
- an automatically registered Mission Control dashboard;
- a native Update entity; and
- Stable and Development update channels with validated installation, backup,
  rollback, and restart handling.

Remaining foundation work includes broader live validation and incremental test
hardening. Fixed calibration values are not user-configurable in Alpha5.2.

## Phase B — Professional UI

**Status: current**

Direction:

- verify and refine 1920 × 1080 TV optimisation;
- meet the no-scroll Mission Control goal for the supported fleet envelope;
- make KPIs consistently actionable;
- improve managed-repeater cards without changing stable entity identity;
- improve chart hierarchy and reduce Level 3 visual competition;
- add accessible repeater detail popups;
- formalise the NOC design language; and
- capture redacted, real-world product screenshots after live validation.

Alpha5.2 provides the TV-first header, compact actionable KPIs,
content-width-aware device grid, dominant 24-hour charts, secondary Trends
view, and compact dashboard-derived alert summary. Detail popups and broader
live proof across real fleet sizes remain future work.

## Phase C — Intelligence

**Status: planned**

- Battery runtime prediction.
- Charging detection.
- Solar performance analysis.
- Battery ageing and degradation.
- Expanded health scoring.
- Smart alerts.
- Trend analysis.

These capabilities require evidence-based models, explainable output, safe
unknown states, and regression tests. The current calibrated battery percentage
and basic health classification should not be described as predictive battery
intelligence.

## Phase D — Network Operations

**Status: planned**

- Network topology.
- Geographic map.
- Link quality.
- Coverage visualisation.
- Device history.
- Site and fleet summaries.

This phase depends on suitable upstream MeshCore data. MeshCore NOC must not
invent topology, location, or link observations that the upstream integration
does not provide.

## Phase E — Version 1.0 Readiness

**Status: planned**

- Stable public API.
- Comprehensive test coverage.
- Complete operator and maintainer documentation.
- Translation support.
- Supported installation workflow.
- Migration guidance.
- Public release checklist.

Version 1.0 also requires a documented compatibility baseline, verified upgrade
and rollback paths, a security review, and clear redistribution terms.

## Roadmap guardrails

- MeshCore remains responsible for source discovery, identity, and raw
  telemetry.
- Existing Home Assistant installations and stable entity IDs must not be
  silently broken.
- Planned work must not be advertised as available.
- The `v3-battery-intelligence` production line remains separate until an
  explicit migration is reviewed and validated.
- Version and release publication follow
  [MH-104 — Release Process](MH-104_Release_Process.md).
