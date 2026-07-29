# MeshCore NOC v1.0 Operational Intelligence Architecture

## Integration boundary constraint

MeshCore NOC will not require modifications to the MeshCore Home Assistant
integration. It will not fork, patch, monkey-patch, or import private MeshCore
modules and will never access serial, BLE, TCP, or meshcore-py directly.
Operational Intelligence may consume only public Home Assistant services,
events, entities, and registry data already exposed by the installed
integration.

Live verification confirmed the read-only `clock` path used by Clock
Intelligence Phase 1. NOC calls public `meshcore.execute_command`, listens to
public `meshcore_raw_event`, and processes only
`EventType.CONTACT_MSG_RECV`. Later mutating commands remain out of scope.

Status: Phase 1 manual checks, Phase 2 fleet orchestration, and dashboard
integration implemented; later mutating phases remain design
Target branch: `main`
Target version: `1.0.0`

This document describes the v1.0 architecture and the implemented manual and
scheduled read-only clock-check slices. It does not claim implemented clock
sync, recovery, maintenance, alert, or persistent historical intelligence.
> **Phase 2 update:** The authoritative MeshCore HA 2.9.0 source confirms a
> generic local-companion command service and a remote repeater `send_cmd`
> transport. Remote text commands currently lack a synchronous, framed,
> correlated response contract suitable for NOC automation. See
> [V4_1_COMMAND_FRAMEWORK.md](V4_1_COMMAND_FRAMEWORK.md) for the source audit
> and proposed split ownership. The installed production version remains to be
> verified.

## Implemented Clock Intelligence Phase 1

The first runtime slice is deliberately read-only and event-driven:

```text
meshcore_noc.check_clock
  -> validate managed repeater and cooldown
  -> meshcore.execute_command
       command: send_cmd <pubkey_prefix> "clock"
  -> wait for meshcore_raw_event
  -> accept only EventType.CONTACT_MSG_RECV
  -> correlate exact pubkey_prefix
  -> parse text and sender_timestamp
  -> publish Clock Offset and Clock Status
```

The service contract uses the NOC stable ID. Its runtime selector contains
only currently managed, addressable repeater stable IDs and shows friendly
names as labels. Friendly names are never accepted as identity. For backward
compatibility, an exact public-key prefix is accepted only when it uniquely
maps to one addressable managed repeater.

The identifier model is deliberately explicit:

| Identifier | Source and purpose |
| --- | --- |
| NOC `stable_id` | Opaque MeshCore-owned device identifier stored in `managed_repeater_ids`; keys discovery, coordinators, clock results, NOC device identifiers, and NOC entity unique IDs |
| MeshCore `public_key` | Full 64-character contact key when exposed by a MeshCore entity; retained as source metadata, never used as the service value |
| MeshCore `pubkey_prefix` | Exact 12-character command address, resolved from ordered MeshCore registry/entity evidence rather than one stable-ID shape |
| Home Assistant device ID | Registry-internal device record ID used to join source entities; never accepted by `check_clock` |
| Source entity ID | Registry/state lookup for telemetry and optional command metadata; mutable and never accepted by `check_clock` |
| Friendly name | Display-only service selector label and device presentation |

The manager never imports MeshCore code or accesses transport objects. It maps
the submitted stable ID to the resolved exact prefix immediately before
calling `meshcore.execute_command`. Requests are single-flight per repeater,
have a fixed response timeout, and obey the configurable conservative
cooldown.

Address resolution is evaluated in priority order and stops at the first
evidence level containing a unique valid prefix:

1. explicit `pubkey_prefix` on MeshCore-owned source metadata;
2. the first 12 characters of an explicit full `public_key`;
3. `pubkey_prefix` or `public_key` on a MeshCore contact entity associated
   with the source device;
4. an unambiguous structured MeshCore device identifier;
5. an unambiguous source entity unique ID; and
6. legacy stable-ID parsing as the final compatibility fallback.

Lower-priority evidence cannot invalidate a stronger uniquely resolved value.
Multiple prefixes at one evidence level are recorded as ambiguous and skipped,
allowing resolution to continue through the existing priority order. A device
is rejected for source ambiguity only after every evidence level is exhausted.
After individual resolution, any prefix shared by multiple managed repeaters is
rejected for all colliding records rather than choosing one silently.

Clock addressability does not depend on an inferred presentation type being
`repeater`. A configured managed device with one unique valid prefix is
accepted when MeshCore type metadata is `repeater` or unavailable/`unknown`.
Only an explicit MeshCore `client` classification is rejected by the type
gate. This prevents incomplete optional model/name metadata from hiding a
valid managed repeater.

The reply text format is `HH:MM - D/M/YYYY UTC`. It is parsed as an aware UTC
datetime and checked against `sender_timestamp`. The signed offset is
`sender_timestamp - Home Assistant receive time`: positive means ahead and
negative means behind. RTT is the best-effort elapsed time from request start
to public reply receipt.

Status thresholds are:

| Internal band | Absolute offset | Sensor state |
| --- | ---: | --- |
| GREEN | <= 30 seconds | In Sync |
| YELLOW | 31–120 seconds | Minor Drift |
| ORANGE | 121–300 seconds | Drift |
| RED | > 300 seconds | Critical |
| UNKNOWN | No successful reply | Unknown |

Diagnostics expose outstanding requests, last request, last response, last
parse result, last timeout, and a rolling in-memory history of 20 attempts.
They also report `managed_repeaters_total`, `addressable_repeaters_total`, and
`non_addressable_repeaters`. Each exclusion contains its stable ID, friendly
name, resolution sources checked, and rejection reason. Per-device discovery
diagnostics include the selected resolution source and whether a full public
key was available. `managed_repeater_addressability` contains one record for
every configured managed device with its stable ID, friendly name, MeshCore
device type, resolution source, resolved prefix if any, all checked sources,
accepted flag, and exact acceptance or rejection reason. No clock sync,
reboot, automatic correction, or persistent history is included.

## Implemented Clock Intelligence Phase 2

Fleet orchestration reuses the Phase 1 Clock Manager and never calls MeshCore
directly. At run start it snapshots the managed, addressable target map in
configured order, reserves every queued stable ID against manual checks, and
processes one repeater at a time:

```text
check_all_clocks
  -> snapshot and reserve addressable stable IDs
  -> check one repeater and await terminal result
  -> wait 15s after success or 30s after failure/timeout by default
  -> dispatch the next repeater
  -> publish summary and release reservations
```

Individual failures, malformed replies, service failures, and timeouts are
recorded and do not stop the remaining queue. A second fleet run is rejected.
Manual single-repeater checks are rejected while that stable ID is queued or
running. Cancellation is cooperative: it does not interrupt an already
transmitted command and stops before the next repeater.

Automatic runs are opt-in and disabled by default. Home Assistant schedules the
first run after the configured interval (six hours by default), never at
startup. Options changes reload the config entry, cancel the old scheduler and
queue task, and calculate a fresh next run. Optional rotating order advances
the starting repeater after each completed run without changing configured
managed order.

Fleet diagnostics include configuration, current run, queue, scheduler state,
next scheduled run, skipped scheduled starts, last summary, the latest 20
in-memory summaries, and non-addressable exclusions. Fleet entities are:

- one per-repeater `button.*_check_clock` attached to each addressable managed
  repeater device;
- `button.check_all_clocks`;
- `button.cancel_clock_check`;
- `sensor.clock_check_progress`;
- `sensor.clock_check_state`;
- `sensor.last_fleet_clock_check`; and
- `sensor.fleet_clock_health`; and
- `binary_sensor.clock_check_running`.

The Mission Control overview includes a compact live fleet clock strip,
health-band counts, controller actions, textual/icon clock severity on each
repeater, and a collapsed detail section with retained offset, last successful
check, latest attempt outcome/error, RTT, response, sender timestamp, bounded
history count, and the per-repeater action. Frontend actions press Home
Assistant button entities and contain no MeshCore command transport.

Mission Control is the primary operational surface. The fleet strip sits
between the eight-tile network summary and repeater grid. It shows active
position, current friendly name, wait/next-check state, progress and outcome
totals; terminal runs show completion time, duration, and expandable
failed/timeout friendly names. The top summary keeps eight tiles by dedicating
one to overall clock severity rather than widening the row. Dashboard controls
derive enabled/busy state from the fleet and per-repeater entities, provide
temporary pending labels and automatically cleared feedback, and surface
Home Assistant action errors without duplicating orchestration.

Successful clock offset/status and their timestamp are retained when a later
attempt times out, fails at the service boundary, or has a malformed reply.
Latest-attempt outcome is independently classified as `success`, `timeout`,
`failed`, or `malformed`. Unknown means no successful reading exists in the
current runtime. Clock and fleet history remain bounded in memory; retained
readings and run state are not restored after restart.

Phase 2 does not set clocks, reboot repeaters, send alerts, or perform automatic
correction.

## Fleet Clock Sync upstream capability gap

Remote clock reading is supported through:

```text
meshcore.execute_command -> send_cmd <repeater> "clock"
```

Local companion time setting is supported through:

```text
set_time(epoch)
```

Remote repeater time setting is not currently exposed through `meshcore_py` or
the Home Assistant MeshCore integration. The firmware `time <epoch>` command
is serial-only. `clkreboot` is not a clock synchronisation mechanism.

Fleet Clock Sync must remain disabled until upstream provides a documented,
remotely addressable clock-set operation with response, authentication,
timeout, and error semantics.

## Goals

- Add explainable operational intelligence for each managed repeater.
- Detect and quantify repeater clock drift relative to Home Assistant time.
- Provide safe, observable manual clock checks, clock sync, reboot, and
  reboot-and-sync recovery.
- Permit explicitly enabled automatic clock management and reboot recovery.
- Add per-repeater Maintenance Mode without stopping telemetry collection.
- Produce actionable, deduplicated, maintenance-aware alerts.
- Derive transparent health from voltage, battery, freshness, clock,
  telemetry, maintenance, and command state.
- Prefer Home Assistant entities, events, services, diagnostics, storage, and
  Recorder conventions.
- Preserve existing config entries, stable IDs, entity identities, source
  ownership, and the production `main` branch.

## Non-goals

- Implementing or guessing an unsupported MeshCore CLI or protocol.
- Replacing the upstream MeshCore integration as connection owner.
- Sending arbitrary operator-provided command text.
- Managing non-selected MeshCore devices.
- Stopping telemetry while a repeater is in maintenance.
- Treating a command write as success without a correlated response and
  post-action verification.
- Building a second time-series database when Recorder can store entity state.
- Changing the v4.0 dashboard or runtime as part of this design task.
- Promising topology, location, or link data not exposed by MeshCore.

## Current architecture summary

### Configuration and lifecycle

MeshCore NOC is a single-instance, config-entry integration. The config flow
requires at least one loaded `meshcore` config entry, discovers MeshCore-owned
registry devices, and stores source config-entry IDs in entry data. Selected
stable IDs and the NOC update channel are stored in entry options. The options
flow replaces the selected set and triggers a full entry reload through the
config-entry update listener.

Setup repeats registry discovery and creates one `MeshCoreNocCoordinator` for
each selected stable ID that still resolves. Unresolved selections remain
configured but have no active coordinator. Unload removes state listeners and
only NOC-owned registry records for explicitly deselected devices.

### Discovery and upstream ownership

Discovery reads Home Assistant device and entity registries. A source device
must be related to a MeshCore config entry and have a `("meshcore",
stable_id)` identifier. Entities are considered only when their platform is
`meshcore`, their config entry belongs to MeshCore, and they belong to the
source device.

Source roles are inferred conservatively from registry metadata and state
metadata. The current roles are voltage, battery percentage, airtime
utilisation, and availability. Names are compatibility fallbacks, never
identity. NOC does not create, update, or delete MeshCore-owned registry
records.

### Coordinators, listeners, and calculations

There is one managed-device `DataUpdateCoordinator` per active selection and a
separate NOC software-update coordinator. A managed-device coordinator:

- polls once per minute;
- subscribes to state changes of the mapped MeshCore voltage entity;
- reads that entity from the Home Assistant state machine;
- uses `last_updated` to calculate telemetry age;
- calculates calibrated voltage, battery percentage, freshness, and basic
  health; and
- exposes last-attempted and last-successful update timestamps.

The state-change listener schedules a debounced coordinator refresh. There are
no MeshCore connection, reconnect, command-response, or registry-change
listeners.

### Entities, services, and events

Each active managed repeater currently has:

- calibrated voltage sensor;
- calibrated battery sensor;
- basic health sensor; and
- freshness binary sensor.

The integration also provides one native software Update entity. MeshCore NOC
does not register a service, button, switch, number, select, or text entity for
repeater control. It does not fire a NOC command event. The updater can call
Home Assistant's own restart service after an integration update; that is not
a repeater reboot capability.

### Diagnostics

Config-entry diagnostics report discovery confidence and warnings, source
entity mappings, configured and active stable IDs, reconciliation, duplicate
detection, updater state, coordinator timestamps, source state, calculations,
freshness, and basic health. Diagnostics do not currently include command
capability, connection state, maintenance, alert lifecycle, clock observations,
or action history.

### Dashboard and frontend

The integration registers a versioned local JavaScript resource and creates or
reuses a storage-mode strategy dashboard without overwriting collisions. The
frontend discovers NOC entities through Home Assistant registries/states,
calculates fleet summaries, and uses native history-graph cards. Those graphs
already rely on Recorder for voltage and battery history. No dashboard control
invokes MeshCore commands.

### Tests and documentation

The Python suite covers config/options flow, registry discovery, coordinator
calculations and listeners, entity identity, setup/reconciliation, diagnostics,
dashboard registration, and software updates. A Node test covers dashboard
logic and lifecycle. Ruff, Python compilation, branding validation, Pytest,
the Node test, and `git diff --check` are the documented checks.

Existing architecture and roadmap documents consistently assign raw discovery,
identity, telemetry, and availability to MeshCore and derived, opt-in
operational behavior to MeshCore NOC.

## Confirmed available interfaces

The following capabilities are confirmed by code in this repository:

| Interface | Evidence and usable contract | Limit |
| --- | --- | --- |
| MeshCore config entries | `hass.config_entries.async_entries("meshcore")` | Presence/provenance only |
| Stable source identity | Device identifier `("meshcore", stable_id)` | Identity is not proven to be a routable command address |
| Source devices/entities | Home Assistant device and entity registries | Registry metadata, not an upstream client object |
| Telemetry states | Home Assistant state machine for mapped entities | Runtime calculation currently reads voltage only |
| State timestamps | `State.last_changed` and `State.last_updated` | Indicates HA state age, not repeater clock |
| Source state changes | `async_track_state_change_event` on voltage entity | No connection/reconnect semantics |
| Optional source roles | Voltage, battery, airtime, availability mappings | Presence and semantics vary by upstream version |
| Config reload | Config-entry update listener | Coarse-grained; not a command channel |
| HA Recorder consumption | Native history-graph cards for NOC sensor states | Recorder retention/configuration is operator controlled |
| NOC diagnostics | Config-entry diagnostic callback | Read-only and currently no command history |
| NOC software update | Separate Update entity/coordinator | Updates NOC files, not repeater firmware or state |

No local source for an installed upstream `meshcore` integration or Python
module was found in the repository, project directories, user tree search, or
the available Home Assistant virtual environment. Consequently, no private
upstream runtime object or undocumented method is accepted as a confirmed
interface.

## Missing interfaces

The following are missing from the confirmed contract:

- a typed capability query per MeshCore device;
- a supported command transport owned by the upstream integration;
- constrained clock-read, clock-set, reboot, or reconnect operations;
- direct-address validation for a command target;
- a command ID and correlated response/result model;
- response framing, parsing, error codes, and timeouts;
- connected/disconnected state for the relevant transport;
- reconnect/disconnect events with session identity;
- confirmation that a reboot caused a disconnect/reconnect;
- upstream concurrency, queueing, and rate-limit guarantees;
- permission or availability signals for destructive commands; and
- a compatibility/version contract for any of the above.

Generic CLI commands, text entities, shell commands, arbitrary service calls,
or guessed runtime-data access must not be used as substitutes.

### Capability classification

- **Confirmed existing:** registry identity/provenance, mapped telemetry entity
  states, state timestamps, voltage state-change events, per-device NOC
  coordinators, config options/reload, diagnostics, Recorder-backed NOC entity
  history.
- **Likely but not safe to depend on:** MeshCore firmware or another client may
  support clock or reboot commands. This was not evidenced in the inspected
  NOC repository or locally installed code.
- **Missing in NOC:** command adapter, lifecycle manager, action services or
  buttons, maintenance model, alert lifecycle, clock model, persistent action
  history, and recovery state machine.
- **Requires live public-interface confirmation:** service execution, target
  addressing, authentication state, public response observation,
  connection/recovery evidence, capability discovery, and safe cooldowns.
  Insufficient public evidence leaves the feature unsupported rather than
  creating a MeshCore integration dependency.

## Clock Intelligence requirements

Clock Intelligence must be capability-gated per repeater. For a supported
device it should:

- read the repeater's timezone-independent instant in a documented format;
- capture local request and response times using timezone-aware UTC;
- estimate clock offset using the request midpoint when protocol precision
  permits;
- store signed offset (`repeater_time - HA_time`), uncertainty/round-trip time,
  observation time, result, and source;
- express positive offset as “ahead” and negative offset as “behind”;
- distinguish unknown, unsupported, stale, checking, within-threshold,
  ahead, behind, and error states;
- provide explicit manual check, sync, reboot, and guarded reboot-and-sync;
- verify sync with a fresh read rather than assuming write success;
- verify reboot through upstream reconnect/session evidence plus telemetry
  recovery, not a fixed sleep alone;
- expose last action, last success, last failure, next allowed action, and
  verification result;
- allow per-installation defaults with optional per-repeater overrides;
- keep all automatic actions disabled by default; and
- refuse clock mutation when HA time is not trustworthy or the offset
  uncertainty exceeds a configured maximum.

Home Assistant time is the reference only after checking timezone-aware system
time and, where available, host synchronization health. NOC must not attempt to
be an NTP implementation.

## Proposed command lifecycle

All commands should pass through one NOC command manager and one upstream
adapter. UI controls, services, and automation must not call transport methods
directly.

1. **Capability check:** confirm the selected stable ID resolves, the operation
   is supported, and a validated upstream address/session exists.
2. **Policy check:** apply maintenance rules, manual/automatic authorization,
   cooldowns, daily limits, connection state, and HA-time trust.
3. **Admission:** acquire a per-repeater lock and a conservative global
   semaphore; reject or coalesce duplicates.
4. **Record intent:** allocate an opaque action ID and persist a redacted
   `queued` record.
5. **Dispatch:** call one typed adapter operation such as `read_clock`,
   `set_clock`, or `reboot`. Never pass arbitrary text from the UI.
6. **Await response:** correlate a documented response to action ID/target and
   transition through `sent` and `response_received`.
7. **Verify:** perform operation-specific verification. Clock writes require a
   readback; reboot requires reconnect/session and telemetry evidence.
8. **Complete:** store `succeeded`, `failed`, `timed_out`, `cancelled`, or
   `verification_failed`, with bounded diagnostic detail.
9. **Publish:** refresh entities/diagnostics and fire one redacted NOC lifecycle
   event if an event API is approved.
10. **Cooldown:** calculate the next permitted action time even after failure.

Cancellation must stop queued work but must not claim an already dispatched
device command was cancelled. Late responses must be recorded as late and must
not mutate a newer action.

## Proposed automatic recovery state machine

The state machine is per repeater and persisted sufficiently to avoid unsafe
retries after Home Assistant restarts.

```text
DISABLED
  -> MONITORING                 automatic management enabled

MONITORING
  -> CHECK_DUE                  observation expired or telemetry/reconnect trigger
  -> SUSPENDED_MAINTENANCE      maintenance enabled

CHECK_DUE
  -> CHECKING                   policy and capability checks pass
  -> COOLDOWN                   blocked by cooldown/rate limit
  -> MONITORING                 no trustworthy transport/time reference

CHECKING
  -> HEALTHY                    offset within threshold
  -> DRIFT_CONFIRMED            repeated trustworthy observations exceed threshold
  -> BACKOFF                    read/transport failure

DRIFT_CONFIRMED
  -> SYNCING                    automatic sync enabled
  -> ALERT_ONLY                 automatic sync disabled

SYNCING
  -> VERIFYING_SYNC             clock-set response received
  -> BACKOFF                    dispatch/response failure

VERIFYING_SYNC
  -> COOLDOWN                   verified within threshold
  -> REBOOT_CANDIDATE           verification failed and reboot recovery eligible
  -> BACKOFF                    verification unavailable

REBOOT_CANDIDATE
  -> REBOOTING                  explicit policy, attempt budget, and cooldown pass
  -> ALERT_ONLY                 otherwise

REBOOTING
  -> WAITING_FOR_RECONNECT      reboot response accepted or documented disconnect
  -> BACKOFF                    dispatch failure

WAITING_FOR_RECONNECT
  -> POST_REBOOT_CHECK          new upstream session/reconnect observed
  -> ALERT_ONLY                 reconnect deadline exceeded

POST_REBOOT_CHECK
  -> VERIFYING_SYNC             clock check followed by sync if still required
  -> COOLDOWN                   clock already healthy
  -> ALERT_ONLY                 attempt budget exhausted

BACKOFF
  -> CHECK_DUE                  bounded exponential backoff expires
  -> ALERT_ONLY                 failure budget exhausted

COOLDOWN
  -> MONITORING                 cooldown expires

SUSPENDED_MAINTENANCE
  -> CHECK_DUE                  maintenance ends; perform observation before action
```

Restart recovery must restore cooldown and attempt budgets, never resume in the
middle of a destructive action, and reconcile any unknown in-flight action as
`outcome_unknown` before new work.

## Maintenance Mode requirements

- Maintenance is per stable ID, with enabled state, start time, optional end
  time, reason, and actor/source.
- Telemetry listeners, coordinator refreshes, calculations, entities, Recorder
  history, and diagnostics continue.
- Automatic sync and reboot recovery are suppressed.
- Manual destructive actions require an explicit confirmation path and are
  recorded; policy may forbid them entirely during maintenance.
- Alerts caused by expected offline, stale, clock, or recovery conditions are
  suppressed or marked maintenance-suppressed, not deleted.
- Safety/integration failures that prevent observation may remain visible.
- Ending maintenance triggers a fresh observation and grace period, not an
  immediate recovery command based on stale evidence.
- Expiry must be timezone-aware and survive restart.

## Smart Alert requirements

Alerts are durable lifecycle records, not repeated notifications. Each alert
has a stable fingerprint derived from stable ID, condition type, and relevant
scope; severity; evidence; first/last observed times; occurrence count; and
state.

Supported states should be `active`, `acknowledged`, `resolved`, and
`suppressed`. Acknowledgement does not resolve the underlying condition.
Resolution requires condition-specific healthy evidence and a debounce window.
Reoccurrence after resolution creates a new occurrence while retaining bounded
history.

Notification policy must:

- notify on meaningful transitions or escalation, not every coordinator poll;
- apply a repeat interval only to still-active, unacknowledged critical alerts;
- suppress maintenance-eligible conditions without losing evidence;
- explain the condition, affected repeater, observed value, threshold, age,
  and safe next action;
- avoid embedding secrets, raw command payloads, or private transport data; and
- remain useful when a command capability is unsupported.

## Operational Health requirements

Health must be deterministic, explainable, and conservative with unknown data.
Inputs are proposed as:

- calibrated voltage and battery band;
- telemetry availability, freshness, age, and recovery trend;
- clock offset, uncertainty, observation age, and capability;
- command/recovery state and recent failures;
- maintenance state; and
- upstream connection state only if a supported interface exists.

The result should expose both a status and ordered reasons. A simple severity
aggregation is preferred initially: the worst active unsuppressed reason
determines `healthy`, `warning`, `degraded`, `critical`, or `unknown`.
Maintenance is a distinct operational overlay, not “healthy.” Missing an
unsupported clock capability must be reported as unsupported and must not make
otherwise valid health critical. Thresholds used in every reason must be
included in attributes/diagnostics.

## Historical Intelligence strategy

Use Recorder for state history where practical:

- calibrated voltage and battery sensors already use measurement state class;
- clock offset should be a measurement sensor in seconds;
- freshness age can be a numeric diagnostic sensor if its historical value is
  operationally useful;
- health and maintenance can be categorical entity states;
- command state should expose current state, not an unbounded attribute list.

Use bounded integration storage for event-like records that Recorder does not
model well: actions, verifications, alert lifecycle, acknowledgements, and
maintenance metadata. Dashboard/history consumers should use Home Assistant
history APIs/cards rather than direct Recorder database access. The design
must tolerate Recorder being disabled, excluded, purged, or configured with a
short retention period.

## Proposed entity model

This is a proposal, not implemented scope.

Per managed repeater:

- `sensor.clock_offset` — signed seconds, timestamp, uncertainty, direction,
  capability and verification attributes;
- `sensor.clock_status` — unsupported/unknown/healthy/ahead/behind/stale/error;
- `sensor.operational_health` — status with ordered reason codes and inputs;
- `sensor.command_status` — current/last action summary only;
- `binary_sensor.telemetry_fresh` — retain existing identity;
- `switch.maintenance_mode` — guarded per-repeater maintenance state;
- `button.check_clock`;
- `button.sync_clock`;
- `button.reboot`; and
- `button.reboot_and_sync`.

Optional configuration entities should use `number`/`switch`/`select` only if
the values are expected to be changed operationally. Otherwise they belong in
the options flow. Destructive buttons must require Home Assistant confirmation
support where available and must remain unavailable without capability.

Existing voltage, battery, health, and freshness unique IDs must remain stable.
The existing health sensor should be migrated or extended deliberately rather
than silently changing its semantics.

## Proposed configuration model

Global defaults in config-entry options:

- automatic clock management enabled: default `false`;
- automatic reboot recovery enabled: default `false`;
- check interval;
- warning and action offset thresholds;
- number of confirming observations;
- maximum observation uncertainty;
- sync cooldown;
- reboot cooldown;
- maximum automatic syncs/reboots per rolling window;
- reconnect and verification timeouts;
- post-maintenance grace period; and
- alert repeat/escalation policy.

Per-repeater overrides should be sparse and keyed by stable ID. Absence means
inherit the global default. Options validation must enforce safe minimums,
threshold ordering, bounded maxima, and no automatic reboot without automatic
clock management. Removing a managed repeater must not modify upstream state.

Temporary maintenance state and action/alert lifecycle do not belong in config
entry options because they change frequently and should not reload the
integration.

## Proposed storage model

Use a versioned Home Assistant `Store` document owned by the config entry:

```text
{
  "schema_version": 1,
  "repeaters": {
    "<stable_id>": {
      "maintenance": {...},
      "recovery": {...cooldowns and attempt budget...},
      "last_clock_observation": {...},
      "actions": [...bounded...],
      "alerts": [...active plus bounded resolved history...]
    }
  }
}
```

Writes should be delayed/coalesced, atomic through Home Assistant storage, and
bounded by count and age. Store redacted enums, timestamps, numeric results,
and short error codes; do not store arbitrary command text, secrets, raw
transport frames, or continuously sampled telemetry. Corrupt or newer-schema
storage must fail safe: disable automatic actions, retain telemetry, expose a
diagnostic error, and avoid destructive repair.

## Safety and rate-limiting requirements

- Automatic mutation is opt-in and off by default.
- Commands are typed and allow-listed; no arbitrary text transport is exposed.
- One in-flight command per repeater and a small global concurrency limit.
- Separate minimum cooldowns for checks, syncs, and reboots.
- Rolling-window action budgets persist across restart.
- Duplicate triggers coalesce against the same condition/action.
- Reboot-and-sync is a bounded workflow, never an unbounded retry loop.
- Manual actions cannot bypass transport capability or an in-flight lock.
- Automatic actions stop during maintenance, uncertain time, missing
  connection evidence, storage failure, or repeated verification failure.
- Target identity is resolved immediately before dispatch and checked against
  the selected stable ID and upstream config entry.
- Logs, diagnostics, events, and storage redact command payloads and transport
  secrets.
- Every mutating action has an audit record and post-action verification.

## Failure handling

- **Unsupported capability:** entities unavailable with an explicit reason;
  monitoring continues.
- **Target unresolved:** do not dispatch; record `target_unresolved`.
- **Disconnected transport:** queue only if the upstream contract explicitly
  supports safe queueing; otherwise fail and back off.
- **Timeout:** mark timed out, retain cooldown, and treat a late response as
  diagnostic evidence only.
- **Malformed/mismatched response:** reject, record, and do not update clock.
- **Clock read uncertainty:** report unknown/stale and take no automatic action.
- **Clock set verification failure:** do not claim success; enter backoff or
  guarded reboot-candidate state.
- **Reboot reconnect timeout:** stop automation and raise one actionable alert.
- **Home Assistant restart:** restore budgets/cooldowns and reconcile in-flight
  actions as unknown outcome.
- **Storage failure:** disable automatic mutation, continue telemetry, and
  surface diagnostics.
- **Recorder unavailable:** current values and bounded action history continue.
- **Upstream reload/removal:** cancel queued work, invalidate adapter/session,
  and rediscover before any future command.

## Migration and compatibility

- Keep config-flow major version and existing entry data/options readable.
- Add new options with defaults; do not require operators to reconfigure.
- Preserve all existing device identifiers, entity unique IDs, and entity IDs.
- Store per-repeater data by MeshCore stable ID, not mutable names or entity
  IDs.
- Treat old entries as automatic-management disabled.
- Add a versioned storage migration before persisting operational data.
- Do not alter the upstream MeshCore config entry, device, or entity registry.
- Keep v4.0 installations functional when command capability is absent.
- Gate new command features by upstream capability/version, with truthful
  unsupported states.
- Document rollback implications for new storage and entities before release.

## Testing strategy

### Unit and integration tests

- adapter contract and capability matrix with a fake upstream implementation;
- target resolution and stable-ID/config-entry ownership checks;
- clock parsing, midpoint offset, direction, uncertainty, and stale handling;
- command lifecycle transitions, correlation, timeouts, late responses, and
  cancellation;
- per-device locks, global limits, cooldowns, budgets, and trigger coalescing;
- state-machine transition table, restart restoration, and attempt exhaustion;
- manual versus automatic policy and Maintenance Mode suppression;
- alert fingerprinting, acknowledgement, resolution, escalation, and dedupe;
- explainable health reason ordering and unknown/unsupported inputs;
- storage round trip, migration, corruption, pruning, and write failure;
- diagnostics redaction and bounded history;
- config/options validation and backward compatibility;
- entity identity, availability, attributes, and Recorder-friendly state; and
- setup, reload, upstream removal, unload, and listener cleanup.

### Proof and system tests

Before feature implementation, create a transport proof of concept against a
real supported MeshCore integration and repeater. Record upstream versions and
verify addressing, clock format/timezone, response correlation, concurrency,
disconnect/reconnect semantics, reboot behavior, and failure modes. No guessed
method should graduate from the proof into production.

Run the existing Python, Ruff, compilation, branding, frontend, and whitespace
checks for every phase. Add time-controlled tests without wall-clock sleeps and
never require a physical repeater in the default unit suite.

## Recommended implementation phases

1. Investigation and architecture.
2. Command transport proof of concept.
3. Manual clock controls.
4. Clock entities and dashboard.
5. Automatic clock recovery.
6. Maintenance Mode.
7. Smart Alerts.
8. Operational Health.
9. Historical Intelligence.
10. Stabilisation and release.

Each phase is gated by tests and documentation. Phase 2 must conclude with a
reviewed existing public Home Assistant contract and live evidence that it is
safe, or a decision that command work cannot proceed. Phases 3–5 cannot proceed
on assumptions.

## Open questions

- Which upstream MeshCore integration version and repository are supported?
- Does it expose a public typed client, service, event, or entity interface?
- Is the stable device identifier also the command address? If not, what is?
- Which device/firmware variants support clock read, set, and reboot?
- What clock format, epoch, timezone, precision, and response framing are used?
- Can responses be correlated by request ID, target, command, or session?
- What indicates connection state and a genuinely new session after reboot?
- Are commands serialized upstream, and what limits/timeouts already apply?
- Can a clock read be safely retried? Can a clock set or reboot?
- How should user identity/actor be captured for manual actions?
- What default thresholds are operationally justified by field data?
- Which alerts remain visible during maintenance?
- Should maintenance be a switch entity, a service with duration/reason, or
  both?
- What Recorder retention and statistics behavior is expected for categorical
  health and signed clock offset?
- How should old basic-health automations transition to expanded health?

## Upstream dependencies

A production implementation may use only existing public Home Assistant
surfaces from the installed MeshCore integration. The minimum usable evidence
is:

- the registered `meshcore.execute_command` schema and response mode;
- a stable public registry/entity value that maps one managed repeater to the
  service's contact argument;
- an authentication path that does not require NOC to read MeshCore private
  config data or retain a repeater password;
- observable service acceptance and send status without treating either as a
  remote response;
- public `meshcore_message` events for optional passive incoming-text
  observation;
- public availability, freshness, and telemetry state sufficient for
  operational verification; and
- installed integration and firmware compatibility evidence gathered through
  supported public diagnostics or UI.

If those existing surfaces are insufficient, command features remain
unsupported in NOC. The project will not modify the MeshCore integration,
import private implementation details, or duplicate its transport.
