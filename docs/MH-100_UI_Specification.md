# MH-100 — MeshCore NOC User Interface Specification

| Field | Value |
| --- | --- |
| Status | Active specification; current and future requirements are identified explicitly |
| Revision | 1.0 |
| Product | MeshCore NOC |
| Baseline | `4.0.0` |

## Product scope

MeshCore NOC is a Home Assistant custom integration that turns selected
MeshCore devices and their raw telemetry into managed operational devices,
calibrated measurements, health and freshness classifications, and a generated
Network Operations Centre dashboard.

The current dashboard is an automatically registered Lovelace strategy. Its
primary Mission Control view includes a compact header, eight KPIs,
managed-repeater cards, the two primary 24-hour Recorder graphs, and
dashboard-derived alerts. A secondary Trends view preserves the seven-day
battery graph and current battery comparison without displacing primary
operations content. It does not currently provide popups, topology, maps,
predictive battery intelligence, or separate alert entities.

## Purpose

The interface gives an operator a rapid, trustworthy view of the selected
MeshCore fleet. Its defining principle is:

> Mission Control, not Lovelace.

Home Assistant remains the platform, but the primary view should read as one
coherent operational console rather than a collection of unrelated cards.

## Target display

- Primary canvas: 1920 × 1080.
- Typical hardware: Samsung TV or a similar wall-mounted display.
- Typical viewing distance: approximately 2–4 metres.
- Primary view: no vertical scrolling at the target resolution.
- Secondary use: desktop, tablet, and mobile access through responsive layouts.

The current Alpha5.2 layout is TV-first and compact, but the no-scroll
requirement across realistic fleet sizes remains a Phase B acceptance target.
Recorder graphs and alerts currently appear below the operational summary.

## Design goals

1. Make abnormal conditions more prominent than decoration.
2. Preserve meaning when telemetry is missing or stale.
3. Keep related metrics spatially grouped.
4. Use stable labels and predictable placement.
5. Remain legible at distance.
6. Degrade safely on smaller screens.
7. Avoid requiring dashboard YAML, custom card installation, or manual entity
   selection.

## Five-second rule

Within five seconds, an operator should be able to determine:

- whether the network is healthy;
- whether any repeaters are offline;
- whether a battery requires attention;
- whether telemetry is stale; and
- whether an active alert requires action.

## Information hierarchy

### Level 1 — immediate action

- Overall network health.
- Offline repeaters.
- Critical alerts.

### Level 2 — device condition

- Battery.
- Voltage.
- Device health.
- Freshness.

### Level 3 — context

- Trends.
- Historical charts.
- Fleet statistics.

Colour, size, contrast, and placement must reinforce this order. Level 3
content must not compete visually with an active Level 1 condition.

## Mission Control layout

The preferred 1920 × 1080 arrangement is:

1. compact Mission Control header;
2. one row of eight KPIs;
3. adaptive managed-repeater grid;
4. compact trends and alerts region where space permits.

Alpha5.2 implements this order in the primary panel view. The overview card
chooses a 1–5-column grid from actual content width and fleet size, with
height-based wide, compact, and constrained density modes.

The primary canvas must avoid nested scrolling. If the managed fleet cannot fit
at a usable text size, the design should prioritise abnormal devices and
provide an explicit path to fleet detail rather than shrinking indefinitely.
That prioritised overflow behaviour is future work.

## Header requirements

The header must show:

- MeshCore NOC identity;
- loaded integration version;
- managed-device count;
- most recent telemetry age when known;
- overall network state; and
- a numeric network-health score when enough observations exist.

Unknown data must be labelled Unknown; it must never be represented as zero or
healthy. Alpha5.2 obtains the displayed installed version from the update
entity, with the loaded integration manifest as a fallback.

## KPI requirements

The current dashboard presents exactly eight operational KPIs:

1. managed devices;
2. online devices;
3. offline devices;
4. active alerts;
5. average battery;
6. lowest battery;
7. fresh devices; and
8. network health.

Values derived from incomplete telemetry must either use only valid
observations with documented weighting or display Unknown. Network health
currently weights availability at 50%, freshness at 30%, and battery condition
at 20%, normalising only observed components. Availability and at least one
telemetry component are required.

## Repeater-card requirements

Each managed-device card must provide:

- normalised device name;
- overall status badge;
- calibrated battery percentage and a clamped battery bar;
- calibrated voltage;
- health;
- freshness; and
- telemetry age when available.

The current backend creates managed devices for every selected MeshCore device
resolved during discovery. Although historical internal names use “repeater,”
discovery may classify a selected source as repeater, client, or unknown.

Cards must:

- preserve the same status semantics everywhere;
- distinguish Unknown from Offline;
- truncate long names without hiding status;
- use colour as a supplement, not the only signal;
- remain readable at the target viewing distance; and
- never expose stable IDs as the primary operator label.

## Graph requirements

Alpha5.2 uses native Home Assistant history graphs for:

- calibrated voltage over 24 hours;
- calibrated battery percentage over 24 hours; and
- battery trend over seven days.

The two 24-hour graphs remain side by side on the primary view where data
exists. The seven-day battery graph and current battery comparison are on the
Trends view. Historical views depend on Home Assistant Recorder; the live
operational summary remains useful without Recorder.

Charts should use restrained grid lines, consistent status colours, readable
units, and explicit empty states. A later chart hierarchy may reduce visual
weight or open history on demand to meet the no-scroll target.

## Alert requirements

Alpha5.2 derives alerts in the dashboard. It flags offline, critical, degraded,
or stale conditions and battery below 15%. These are presentation-level alerts,
not persistent alert entities or notifications.

An alert must identify the affected device and the reason. “No active alerts”
must be a positive, low-emphasis state. A future alert system may add
acknowledgement, persistence, routing, and smart thresholds, but those features
are not part of the current implementation.

## Interaction requirements

Current interactions are intentionally limited:

- live entity state updates;
- automatic refresh after device or entity registry changes;
- normal Home Assistant history-card interaction;
- integration configuration through Devices & services; and
- update installation through the native Update entity.

Primary status must not depend on hover. Keyboard focus must remain visible for
interactive controls. Touch targets should be at least 44 × 44 CSS pixels when
new controls are introduced.

## Responsiveness

- At wide widths, KPIs should occupy one row and device cards should use the
  available grid.
- The responsive engine measures actual card width rather than assuming
  physical screen width.
- At 1,450 px or more, fleets of 17–20 devices can use five columns.
- At 1,050 px or more, fleets above four devices use four columns.
- Below 1,050 px, larger fleets use three columns.
- Below 700 px, the layout uses one device-card column; KPIs collapse from
  four columns to two through container-aware CSS.
- Content must reflow without horizontal scrolling.
- The mobile layout may scroll vertically; the no-scroll requirement applies
  to the primary 1920 × 1080 operations display.

## Accessibility

- Meet WCAG 2.1 AA contrast for text and essential graphical indicators.
- Pair colour with labels, icons, or shape.
- Provide meaningful Unknown, unavailable, and empty states.
- Respect browser text scaling.
- Maintain logical reading order and semantic headings.
- Do not use flashing content.
- When animation is added, respect `prefers-reduced-motion`.

## Performance

- Reuse Home Assistant state and registry data already available to the
  strategy.
- Avoid polling from the frontend.
- Batch registry reads during dashboard generation.
- Re-render only when state or relevant registry data changes.
- Keep the frontend bundle dependency-free and locally served.
- Ensure the operational summary remains responsive on typical TV browser
  hardware.

## Future detail-popup behaviour

Repeater detail popups are planned, not implemented in Alpha5.2. A future popup
should:

- open from a repeater card without changing the stable device identity;
- show voltage, battery, health, freshness, source, and recent history;
- keep the main dashboard state visible behind it;
- close by keyboard, pointer, or Back action;
- trap focus appropriately and restore focus on close;
- work without hover; and
- avoid placing essential alarms only inside the popup.

Popup routing must remain stable across display-name changes by using the
managed device’s stable identifier internally.

## Acceptance criteria

- [ ] At 1920 × 1080, Level 1 conditions are visible without scrolling.
- [ ] An operator can satisfy the five-second rule.
- [ ] The header shows identity, loaded version, count, age, state, and score
      without inventing missing values.
- [ ] Eight KPI meanings are consistent with backend and dashboard logic.
- [ ] Every selected, resolved managed device has one card with voltage,
      battery, health, and freshness.
- [ ] Offline, stale, degraded, critical, and unknown conditions are
      distinguishable without colour alone.
- [ ] Current values remain usable when Recorder is disabled.
- [ ] Mobile and tablet layouts do not overflow horizontally.
- [ ] Keyboard and screen-reader users can reach every interactive control.
- [ ] Motion is subtle, optional, and never required to understand state.
- [ ] Future-only capabilities are visibly labelled as planned.
