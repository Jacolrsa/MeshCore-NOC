# MeshCore NOC v1.1.0 Beta 4 dashboard

Beta 4 changes dashboard presentation only. Existing discovery, entities,
services, stable identifiers, clock orchestration, automatic scheduling and
diagnostics remain the operational source of truth.

## Mission Control

The main view uses one compact Network Status header for:

- overall state, managed/online counts and active issues;
- concise, navigable alert chips;
- last fleet synchronisation and fleet clock health;
- automatic-synchronisation state;
- Check All, Sync All and active-check cancellation; and
- current fleet operation progress.

Below the header, the fleet list occupies approximately 28 percent of desktop
width and the recorder-backed calibrated-voltage chart occupies the remaining
space. Each row uses text and an icon/status indicator in addition to colour
and opens a deterministic repeater subview.

The chart is bundled with MeshCore NOC rather than requiring an additional
custom dashboard card. It offers 24-hour, 7-day and 30-day ranges, uses short
repeater names, excludes unknown, unavailable, non-numeric, negative and
implausible voltage history, and uses automatic fleet-relative scaling.

## Repeater detail views

Each managed repeater receives a generated subview containing:

- a concise status header and return link;
- one calibrated-voltage history chart;
- monitoring values and last-heard age;
- the existing per-repeater Check Clock button;
- the existing `meshcore_noc.sync_repeater_clock` service;
- current and retained clock results, responses and errors;
- read-only source identity and public addressing;
- read-only calibration values and live calculated previews; and
- collapsed source and clock diagnostics.

## Persistent settings boundary

The current integration has no per-repeater persistence model for display
names, visibility/order, notes/location, calibration overrides, reset
calibration, freshness thresholds, battery thresholds, or clock thresholds.
Beta 4 does not present fake editable controls for those fields.

Existing persistent fleet clock options remain available through the MeshCore
NOC config-entry options. Home Assistant device naming remains available
through the device settings link. Per-repeater overrides are deferred until a
validated integration-backed storage and migration design is implemented.

## Recorder behaviour

The chart reads Home Assistant Recorder history through the authenticated
frontend API. Current telemetry and all operational controls remain available
if Recorder is disabled or history cannot be loaded; the chart displays a
contained unavailable message rather than breaking the view.
