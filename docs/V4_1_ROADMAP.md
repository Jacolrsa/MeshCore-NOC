# MeshCore NOC v1.0 Operational Intelligence Roadmap

Status: proposed
Release version: `1.0.0`
Release branch: `main`

This roadmap is an ordered engineering plan, not a statement of implemented
functionality or a delivery commitment. Implemented read-only Clock
Intelligence ships in the `1.0.0` public release.

## Phase 1: Investigation and architecture

- Audit current NOC and upstream interfaces.
- Document confirmed capabilities, gaps, safety boundaries, entity/config
  proposals, persistence, testing, and upstream dependencies.
- Keep runtime and dashboard behavior unchanged.

Exit gate: reviewed architecture with unsupported interfaces clearly marked.

## Phase 2: Command transport proof of concept

- Identify the supported upstream MeshCore integration and version.
- Validate typed target addressing, clock read, clock set, reboot, responses,
  timeouts, connection state, and reconnect evidence against real hardware.
- Use only public interfaces already exposed by the installed MeshCore
  integration; do not require integration changes.
- Live verification on 2026-07-28 was blocked because the actual Home Assistant
  environment was not accessible. Source verification confirmed that the 2.9.0
  generic `send_cmd` path reports send acceptance but exposes no supported,
  correlated remote CLI reply to NOC.
- Run `V4_1_EXISTING_SERVICE_LIVE_TEST.md` to verify the public service schema,
  target mapping, authentication, service response, public message events, and
  source-state evidence before adding NOC runtime command code.
- **Implemented first slice:** manual read-only `clock` checks now use
  `meshcore.execute_command` and exact-prefix correlation on public
  `meshcore_raw_event` `EventType.CONTACT_MSG_RECV` replies. They expose signed
  offset/status diagnostics with timeout, per-target single-flight, cooldown,
  and bounded in-memory history.
- **Implemented second slice:** manual and opt-in scheduled fleet clock checks
  now run through a one-at-a-time queue with per-result delays, collision
  protection, cooperative cancellation, optional rotating start, fleet-level
  entities, diagnostics, and bounded in-memory run history.
- **Implemented dashboard slice:** per-repeater Home Assistant Check Clock
  buttons, retained successful values with independent attempt outcomes,
  fleet health counts, and compact live Mission Control controls/details.
- **Implemented operational refinement:** Mission Control is the primary clock
  control surface with active/terminal fleet detail, an eight-tile health
  summary, entity-derived busy states, and non-intrusive action feedback.

Exit gate: met for the read-only manual and fleet `clock` slices. Mutating
commands remain separately gated. No guessed private API and no MeshCore
integration modification.

## Phase 3: Manual clock controls

- Extend the implemented read-only command manager and bounded action lifecycle.
- Add separately gated manual sync, reboot, and guarded reboot-and-sync.
- Add verification, cooldowns, locks, audit history, and failure reporting.

Exit gate: manual actions are capability-gated, correlated, verified, and
covered by failure-path tests.

## Phase 4: Clock entities and dashboard

- **Implemented read-only scope:** Recorder-friendly clock offset/status,
  successful-reading age, latest-attempt metadata, fleet health, per-repeater
  and fleet button controls, and compact dashboard presentation.
- Persistence across restart, direction/uncertainty expansion, verification,
  and all mutating controls remain future work.

Exit gate: entity identity and frontend behavior are stable, accessible, and
truthful for supported, unsupported, unknown, and error states.

## Phase 5: Automatic clock recovery

- Add opt-in checking and sync policy.
- Add the persisted recovery state machine, thresholds, cooldowns, attempt
  budgets, backoff, and guarded reboot recovery.
- Keep all automatic mutation disabled by default.

Exit gate: deterministic time-controlled tests cover every state and restart.

## Phase 6: Maintenance Mode

- Add per-repeater maintenance state, optional expiry, reason, and audit data.
- Continue telemetry while suppressing eligible alerts and automatic recovery.
- Add post-maintenance grace and fresh observation.

Exit gate: maintenance cannot silently stop telemetry or trigger stale recovery.

## Phase 7: Smart Alerts

- Add stable alert fingerprints and active, acknowledged, resolved, and
  suppressed lifecycle states.
- Add escalation, deduplication, repeat limits, and maintenance-aware policy.
- Provide actionable evidence and next steps.

Exit gate: repeated coordinator updates cannot create notification spam.

## Phase 8: Operational Health

- Combine voltage, battery, freshness, clock, telemetry, maintenance, and
  recovery evidence.
- Expose deterministic status and ordered reasons.
- Preserve unknown and unsupported distinctions.

Exit gate: every status is explainable from exposed inputs and thresholds.

## Phase 9: Historical Intelligence

- Use Home Assistant Recorder for numeric and categorical entity history.
- Add bounded storage/query paths for action, verification, alert, and
  maintenance history.
- Degrade cleanly when Recorder is disabled or purged.

Exit gate: history is bounded, redacted, migration-safe, and does not duplicate
the Recorder database.

## Phase 10: Stabilisation and release

- Complete regression, migration, failure-injection, live hardware, frontend,
  security, rate-limit, update, rollback, and documentation validation.
- Finalize compatibility requirements and release notes.
- Follow the existing release process; do not merge, tag, or publish early.

Exit gate: explicit maintainer release approval and all release checks pass.

## Cross-phase guardrails

- MeshCore owns connection, raw identity, raw telemetry, and device transport.
- NOC consumes only supported, versioned upstream interfaces.
- MeshCore NOC will not require modifications to the MeshCore Home Assistant
  integration.
- Stable IDs and existing NOC entity identities remain compatible.
- Automatic clock mutation and reboot recovery are opt-in.
- Every mutation is rate-limited, auditable, and verified.
- Maintenance preserves telemetry.
- Planned features are never presented as currently available.
- `main` remains production-ready throughout operational-intelligence development.
