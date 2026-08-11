# MeshCore NOC 1.1.0

MeshCore NOC 1.1.0 promotes the clock-management and Mission Control work from
the 1.1 beta series into the stable product line.

## Scope

1.1.0 focuses on four areas:

1. authenticated repeater clock checks;
2. anti-replay-safe, latency-aware clock synchronisation;
3. unattended fleet automation with credential safeguards; and
4. Mission Control usability, including fleet severity and Recorder graph
   stability/interactivity.

The upstream MeshCore integration remains the source of truth for device
identity, radio transport, routing and raw telemetry.

## Authenticated clock checks

Clock checks require the saved administrator password for the target repeater.
The normal sequence is:

```text
password login
  ↓
MeshCore route-specific suggested_timeout
  ↓
LOGIN_SUCCESS
  ↓
short radio settle
  ↓
clock command
  ↓
MeshCore route-specific suggested_timeout
  ↓
clock reply
```

The route timeout comes from the actual transmission. Direct repeaters can
therefore complete quickly while multi-hop/flood-routed repeaters receive a
longer valid response window.

The clock-command RTT is measured independently from the login transaction.
Displayed offset compensates approximately half of that RTT so the return radio
path is not reported entirely as RTC drift.

## Clock synchronisation

Home Assistant UTC is authoritative.

Before writing anything, NOC performs the normal authenticated clock check. If
the latency-corrected repeater offset is already within ±30 seconds, the sync
returns success without rebooting the repeater and without writing its clock.

When correction is required, NOC uses the anti-replay-safe sequence developed
during field testing:

```text
authenticated pre-check
  ↓
repeater replay-safe reset/login sequence when needed
  ↓
verify connected companion time against Home Assistant UTC
  ↓
repair ahead-running companion only when required
  ↓
latency-compensated clock sync timestamp
  ↓
authenticated latency-aware verification
```

A sync is successful only when the final verified offset is within ±30 seconds.

## Companion clock recovery

Some companion firmware only accepts normal `set_time` operations that move the
clock forward. A companion that is already in the future can also persist the
problem because contact `lastmod` timestamps are used to seed the RTC after
reboot.

The v1.1 recovery path:

- reads the companion clock and Home Assistant UTC;
- identifies only contacts whose saved `lastmod` is in the future;
- preserves contact identity, path, flags, name, advert time and coordinates;
- rewrites only the invalid future `lastmod` field;
- waits for the firmware's delayed contact persistence window;
- reboots and verifies the companion;
- then uses normal forward-only time setting to reach Home Assistant UTC.

No contact deletion or factory reset is part of this workflow.

## Repeater anti-replay recovery

A repeater may remember a previously accepted future administrator timestamp.
After the companion is corrected backwards, otherwise-valid commands can look
like replayed old traffic.

The v1.1 recovery path can reset that transient repeater replay state, reboot the
repeater and then resume normal password-authenticated operations using the
correct time base.

## Fleet automation

### Automatic checks

Automatic fleet checks are serialized. One repeater transaction completes,
fails or times out before the next target begins.

### Automatic sync

Automatic sync is disabled by default and supports 6, 12, 24, 72 and 168 hour
intervals.

An unattended automatic sync does not start unless every managed addressable
repeater has a saved administrator password. This prevents a partially
configured fleet from entering a scheduled write/reboot workflow.

Repeaters already within ±30 seconds are skipped without clock modification.

## Options cleanup

The 1.1 options screen exposes only active operator controls:

- managed devices;
- Stable/Development update channel;
- automatic clock-check enable and interval; and
- automatic clock-sync enable and interval.

Legacy manual cooldown, success-delay, failure-delay and rotating-start values
may remain in stored config-entry options for rollback compatibility, but they
are not part of the normal 1.1 UI.

## Fleet severity

Mission Control fleet rows now use the worst current condition across:

- availability/health/freshness;
- battery thresholds; and
- clock state.

The row's left border, status dot and repeater name use the resulting severity
colour. Individual voltage, battery and clock values remain separately readable.

## Recorder graph

The 1.1 graph remains a dependency-free custom Home Assistant web component.
It reads Recorder history directly.

### Ranges

- 6 hours
- 24 hours
- 7 days
- 30 days

### Background refresh

The graph keeps the last good SVG visible while Recorder refreshes in the
background. Home Assistant state updates can therefore trigger a history refresh
without the graph clearing to a Loading state.

If a temporary Recorder/API refresh fails, the last good graph remains visible
and the refresh status reports the failure.

### Interaction

- time/date labels on the x-axis;
- current value and period change in the legend;
- click legend entries to hide/show series;
- crosshair and timestamped values on pointer movement;
- preserved Recorder gaps;
- large instantaneous calibration/Recorder jumps are shown as a break instead
  of a vertical line that could be mistaken for a real battery event.

## Password storage

Repeater passwords are stored in Home Assistant private storage. Browser reads
return only whether a password exists and when it was last changed. Passwords
are not exposed through entities, normal diagnostics or command transcripts.

## Upgrade notes

- Install/redownload 1.1.0 and perform a full Home Assistant restart.
- Existing managed stable IDs, entity identities and per-repeater settings are
  retained.
- A hard browser refresh may be required after upgrading the frontend bundle.
- Existing beta users do not need to remove and re-add the config entry.

## Validation checklist

After upgrade:

1. Confirm Mission Control loads and fleet severity colours are visible.
2. Run **Check this repeater** on one direct and one routed repeater.
3. Run **Check All** and confirm routed repeaters use longer response windows
   rather than fixed short timeouts.
4. Run **Sync All** once manually. Repeaters already within ±30 seconds should
   report that no clock write was required.
5. Leave Mission Control open for several minutes and confirm Recorder refreshes
   no longer blank/reload the graph.
6. Enable automatic sync only after all managed repeaters show a saved
   administrator password.

See also [README](../README.md), [Troubleshooting](troubleshooting.md), and
[Update channels](updates.md).
