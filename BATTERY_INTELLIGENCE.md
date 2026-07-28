# MeshCore NOC Battery Intelligence

## Goal

Design a reusable battery intelligence subsystem for MeshCore NOC.

The dashboard must never own calibration.
Calibration belongs to the repeater.

The subsystem must expose stable, calibrated entities that dashboards,
graphs, statistics, alerts, and automations can consume without knowing how
calibration is performed.

### Scope Boundary

AI and machine learning are out of scope.

Runtime estimates, forecasts, battery-health assessments, and maintenance
recommendations must use deterministic formulas, rolling averages, explicit
thresholds, and visible historical measurements. Every result must be
traceable to its inputs and calculation method.

The subsystem must not use opaque models, probabilistic AI recommendations,
or machine-learning predictions.

### Current Scope

The initial implementation includes:

- Independent per-repeater calibration.
- A linear battery-percentage calculation.
- Safe validation of raw voltage, calibration parameters, and derived values.
- Backward-compatible migration using existing entity IDs where technically
  possible.

The following are future capabilities and are not part of the initial
calibration implementation:

- Chemistry-specific and custom battery profiles.
- Deterministic operational analytics.
- Runtime and replacement forecasting.
- Battery Passport records.
- Calibration and maintenance history.

---

## Objectives

Every repeater must support independent calibration.

Each repeater stores:

- Voltage Offset
- Empty Voltage
- Full Voltage
- Battery Profile
- Calibration Date
- Calibration Confidence
- Calibration Schema Version
- Battery Profile Schema Version
- Calibration Provenance

The dashboard only displays the calculated values.

Calibration settings must be managed outside dashboard configuration. A
change to one repeater's calibration must not affect any other repeater.

Each repeater's Home Assistant package is the source of truth for that
repeater's calibration helpers and metadata. There must be no global voltage
offset, empty voltage, full voltage, or calibration record. Shared
configuration may define schemas and profile definitions, but never a
repeater's selected calibration values.

The subsystem must:

- Preserve stable entity IDs.
- Reject unavailable, non-numeric, and physically invalid inputs.
- Keep calibration parameters visible and auditable.
- Support gradual migration, one repeater at a time.
- Provide a foundation for chemistry-aware discharge curves and
  deterministic forecasting implemented with visible calculations.

---

## Architecture

```text
MeshCore Raw Voltage

↓

Per-Repeater Calibration

↓

Calibrated Voltage

↓

Calculated Battery Percentage

↓

Dashboard
Graphs
Statistics
Alerts
Automations
```

The raw voltage entity is the source measurement received from a repeater.
It must remain unchanged and should be retained for diagnostics.

Per-repeater calibration applies that repeater's voltage offset only after
all inputs have been validated.

```text
calibrated_voltage = raw_voltage + voltage_offset
```

The calibrated voltage is then evaluated against the selected battery
profile and the repeater's empty and full voltage settings.

For the initial linear profile, the exact calculation sequence is:

```text
1. Validate raw_voltage, voltage_offset, empty_voltage, and full_voltage.
2. Require full_voltage > empty_voltage.
3. calibrated_voltage = raw_voltage + voltage_offset
4. percentage =
     ((calibrated_voltage - empty_voltage) /
     (full_voltage - empty_voltage)) × 100
5. battery_percentage = min(100, max(0, percentage))
6. Return unavailable if any input or calibration range is invalid.
```

Equivalent percentage formula:

```text
battery_percentage =
  ((calibrated_voltage - empty_voltage) /
  (full_voltage - empty_voltage)) × 100
```

Only a valid calculated percentage is constrained to the display range of
0–100%. Invalid measurements and invalid calibration ranges must become
unavailable rather than being clamped or forced to a plausible value.

### Invalid Voltage Rules

A voltage is invalid when it is:

- Unknown, unavailable, null, empty, or non-numeric.
- A non-finite number.
- A known transport, firmware, or sensor-error sentinel.
- Outside the configured physical limits for the repeater and selected
  battery profile.
- Below the minimum plausible raw-voltage threshold defined by the
  calibration schema.
- A calibrated voltage outside the selected profile's permitted diagnostic
  range.

Physical limits must be schema-controlled and visible. They must not be
embedded in dashboards.

Calibration parameters are configuration inputs. Calibrated voltage and
battery percentage are derived outputs. The dashboard consumes only the
derived outputs.

### Source of Truth

- The per-repeater Home Assistant package owns calibration helpers,
  calibration metadata, provenance, and selected profile.
- Shared files own schema definitions and reusable battery-profile
  definitions only.
- Template sensors own live calculations.
- Recorder owns recorded historical states.
- A separate recalculation service or script owns non-destructive historical
  recalculation outputs.
- The dashboard remains presentation only and never stores or calculates
  calibration data.

---

## Default Values

### Voltage Offset

`-0.816 V`

### Empty Voltage

`3.000 V`

### Full Voltage

`4.200 V`

### Battery Profile

`18650 Li-ion`

These become defaults only.

Every repeater can override them.

Defaults provide backward-compatible behavior during migration. They must
not become global constants embedded in dashboards, automations, or shared
template logic.

### Schema Versions

Every repeater calibration record must include a calibration schema version.
Every selected battery profile must include a battery-profile schema version.

Schema versions make validation rules, field meanings, and discharge curves
auditable over time. A schema upgrade must be explicit and must not silently
reinterpret existing calibration or historical data.

Recommended metadata:

```text
calibration_schema_version: 1
battery_profile_schema_version: 1
```

---

## Home Assistant Components

### Input Number Helpers

Each repeater should have independent helpers for:

- Voltage offset
- Empty voltage
- Full voltage
- Optional manually measured voltage used during guided calibration
- Optional confidence score if confidence is represented numerically

Recommended characteristics:

| Helper | Minimum | Maximum | Step | Unit |
|---|---:|---:|---:|---|
| Voltage offset | -2.000 | 2.000 | 0.001 | V |
| Empty voltage | 2.000 | 4.500 | 0.001 | V |
| Full voltage | 2.500 | 5.000 | 0.001 | V |
| Measured voltage | 0.000 | 6.000 | 0.001 | V |
| Confidence | 0 | 100 | 1 | % |

Helper IDs should include a stable repeater slug. For example:

```text
input_number.promicro_voltage_offset
input_number.promicro_empty_voltage
input_number.promicro_full_voltage
input_number.promicro_measured_voltage
input_number.promicro_calibration_confidence
```

Battery profile selection should use an `input_select` helper:

```text
input_select.promicro_battery_profile
```

Calibration date can use `input_datetime`:

```text
input_datetime.promicro_calibration_date
```

Calibration provenance should be stored per repeater and include:

- Operator
- Multimeter make, model, or identifier
- Repeater load state during measurement
- Calibration notes

Text provenance may use per-repeater `input_text` helpers or another
auditable storage mechanism owned by the repeater package.

### Restored Helper Validation

Home Assistant restores helper states after restart. Restored values must be
treated as untrusted inputs until validated.

After every restart, template availability logic must verify:

- Every helper is numeric where required.
- Full voltage is greater than empty voltage.
- Offset and voltage bounds comply with the calibration schema.
- The selected profile exists and its schema version is supported.
- Required calibration metadata is present.

If validation fails, calibrated voltage and battery percentage must return
unavailable. The system must expose a calibration-invalid diagnostic and must
not silently replace an invalid restored value with a default.

### Template Sensors

Each repeater should expose:

- Raw voltage
- Calibrated voltage
- Calculated battery percentage
- Calibration validity
- Calibration age
- Battery profile
- Optional calibration confidence

Template sensors must:

- Convert source states to numbers explicitly.
- Return unavailable when the raw value or calibration parameters are
  unavailable.
- Verify that full voltage is greater than empty voltage.
- Reject values outside agreed physical limits.
- Include appropriate device class, state class, and units.
- Round only the published state, not intermediate calculations.
- Calculate live values only; they do not rewrite recorder history.

The calibrated voltage and battery percentage entity IDs already used by
MeshCore NOC must remain stable.

### Packages

Home Assistant packages are the preferred unit of configuration because
they keep each repeater's helpers, templates, scripts, and automations
together.

Each repeater package should contain:

- Calibration helpers
- Profile selector
- Calibration metadata
- Calibrated voltage template sensor
- Battery percentage template sensor
- Calibration validation sensor
- Guided calibration script
- Optional maintenance automations

A shared package may define common profile metadata and reusable conventions,
but it must not hold per-repeater calibration values.

Each repeater package is authoritative for its own helper values, selected
profile, calibration date, confidence, provenance, and schema versions.

### Recommended File Structure

```text
config/
├── configuration.yaml
├── packages/
│   └── meshcore/
│       ├── common.yaml
│       ├── profiles.yaml
│       ├── promicro.yaml
│       ├── myburgh_park.yaml
│       ├── saldanha.yaml
│       ├── vredenburg.yaml
│       ├── vredenburg_ne.yaml
│       ├── laguna_2.yaml
│       ├── promicro_test.yaml
│       └── test_solar.yaml
├── templates/
│   └── meshcore_battery.yaml
└── automations/
    └── meshcore_battery.yaml
```

If Home Assistant package loading does not support nested directories in the
active installation, use a single `packages/meshcore_<repeater>.yaml` file
per repeater.

The recommended ownership boundary is:

- Repeater package: calibration and derived entities
- Shared profiles file: chemistry definitions and curve metadata
- Automations: notifications and maintenance workflows
- Dashboard: presentation only

---

## Future Battery Profiles

The subsystem must support the following profiles.

### 18650 Li-ion

Default nominal lithium-ion profile with a typical full voltage near 4.2 V.
The exact empty voltage remains configurable per repeater.

### LiPo

Lithium-polymer profile with voltage behavior similar to common lithium-ion
cells but potentially different safe limits, loading behavior, and discharge
curve.

### LiFePO4

Lithium iron phosphate profile with a flatter discharge plateau and different
full and empty voltages. A linear percentage calculation is particularly
inaccurate for this chemistry.

### Custom

A user-defined profile with configurable empty and full voltage values and,
later, a custom discharge curve.

### Discharge Curves

The initial implementation can retain a linear calculation between empty and
full voltage. A future profile engine should replace the linear calculation
with piecewise interpolation.

Example profile data:

```text
Voltage → Remaining capacity
4.20 V  → 100%
4.05 V  → 85%
3.90 V  → 65%
3.75 V  → 35%
3.50 V  → 10%
3.00 V  → 0%
```

The calculation would locate the measured voltage between two curve points
and interpolate the percentage. Profile curves should be versioned so a
profile update does not silently rewrite historical interpretation.

Temperature, load, cell age, and voltage recovery after load removal may
later become profile inputs.

---

## Future Analytics

### Estimated Runtime

Runtime estimation is a conventional deterministic calculation:

```text
estimated_runtime =
  remaining_usable_capacity /
  rolling_discharge_rate
```

Remaining usable capacity comes from the selected battery profile, rated
capacity, current calculated percentage, and any deterministic health
adjustment. The rolling discharge rate comes from valid historical
measurements over documented time windows.

An estimate requires, at minimum:

- A configured rated capacity.
- A supported battery profile.
- At least 24 hours of valid history.
- At least 12 valid samples.
- At least 6 samples showing a consistent non-zero discharge trend.
- No calibration change, battery replacement, or charging period inside the
  selected estimation window.
- A positive discharge rate above the configured noise floor.

If these requirements are not met, estimated runtime must be unavailable.
The implementation must not extrapolate from insufficient or contradictory
data.

Runtime output must expose analytics confidence separately from calibration
confidence. Calibration confidence describes measurement calibration
quality. Analytics confidence describes history coverage, sample quality,
trend stability, and calculation reliability.

### Charge Rate

Calculate the rate of battery percentage or voltage increase over a rolling
window. Ignore isolated spikes and calibration changes.

### Discharge Rate

Calculate percentage loss per hour and voltage loss per hour over multiple
windows. Longer windows should be preferred for slowly updating repeaters.

### Battery Health

Compare observed runtime, charge behavior, resting voltage, and discharge
curve against the selected profile's expected behavior. Health should be
reported as a trend or grade, not inferred from a single reading.

### Charging Detection

Detect charging from a sustained positive voltage or percentage trend.
Require multiple samples to prevent normal measurement noise from toggling
the state.

### Battery Replacement Forecasting

Use deterministic trend projection to estimate when usable runtime or battery
health will fall below an operational threshold. Forecasts must include the
formula, source window, last evaluation time, analytics confidence, and
amount of supporting history.

Analytics must distinguish:

- Real telemetry
- Missing telemetry
- Calibration changes
- Battery replacements
- Charging periods
- Sensor resets

Calibration or replacement events must break trend windows so that artificial
steps are not interpreted as charge or discharge rates.

---

## Battery Passport

The Battery Passport is a dedicated subsystem and lifecycle record for every
physical battery. It is separate from calibration, battery profiles,
analytics, and dashboard presentation.

Each passport must contain:

- Battery identifier
- Assigned repeater
- Chemistry/profile
- Manufacturer
- Model
- Rated capacity
- Installation date
- Removal date
- Calibration association
- Service history
- Health observations
- Replacement reason
- Notes

The battery identifier must remain stable when the battery moves between
repeaters. Assignment history must record when a battery was attached to or
removed from a repeater.

Calibration association links a passport to the calibration records that were
valid while that battery was installed. It must not copy or globally own a
repeater's calibration values.

Battery Passport records should be append-oriented and auditable. Replacing a
battery closes the active assignment and creates or activates the passport for
the replacement battery. Historical passports must remain readable.

The initial passport implementation may use structured files or another
auditable Home Assistant-compatible store. Dashboard cards may display
passport data, but dashboards must not be the source of truth.

---

## Calibration Workflow

The guided process should be implemented as a Home Assistant script or
assisted workflow.

### 1. Measure Battery With a Multimeter

Measure the battery directly while the repeater is in a known and stable
operating state. Record whether the device was charging, idle, or under load.
Record the operator, multimeter identifier, load state, and calibration notes
as provenance.

### 2. Enter Measured Voltage

Enter the multimeter reading into the repeater's measured-voltage helper.
The workflow must show the current raw MeshCore voltage alongside the entered
value.

### 3. Automatically Calculate Offset

Calculate:

```text
new_offset = measured_voltage - raw_voltage
```

Do not calculate an offset if either value is unavailable or outside
reasonable physical limits.

### 4. Review and Save Calibration

Display:

- Repeater name
- Raw voltage
- Measured voltage
- Existing offset
- Proposed offset
- Resulting calibrated voltage
- Difference from the previous calibration

Saving must require an explicit confirmation.

### 5. Record Calibration Date

Set the repeater's calibration date to the current date and time when the new
offset is saved.

### 6. Update Confidence

Confidence should reflect the quality of the calibration:

- High: stable reading, recent multimeter measurement, repeated agreement
- Medium: single valid measurement under known conditions
- Low: old calibration, unstable telemetry, or uncertain load state
- Unknown: migrated default with no repeater-specific measurement

Confidence may initially be selected manually. A later implementation can
calculate it from calibration age, sample stability, and repeated
measurements.

Calibration confidence must remain distinct from analytics confidence.
Changing one must not silently change the other.

The workflow should create a maintenance log entry containing the old and new
values, operator, multimeter, load state, notes, schema versions, and
confidence.

---

## Migration Plan

The migration starts from the existing fixed `-0.816 V` calibration.

### Compatibility Requirements

No dashboards break.

No automations break.

No graphs break.

Existing entity IDs remain usable.

Migration can be performed repeater by repeater.

Stable entity IDs must be preserved where technically possible. Continuity
depends on Home Assistant entity-registry behavior, template entity
configuration, unique IDs, and the migration method used by the installed
Home Assistant version.

### Migration Strategy

1. Inventory every raw, calibrated, and battery-percentage entity.
2. Record the entity IDs currently consumed by dashboards and automations.
3. Introduce per-repeater helpers with the existing values as defaults:
   - Offset: `-0.816 V`
   - Empty: `3.000 V`
   - Full: `4.200 V`
   - Profile: `18650 Li-ion`
4. Move the calculation into each repeater's package.
5. Publish the new template sensor using the existing calibrated-voltage
   entity ID.
6. Publish battery percentage using the existing percentage entity ID.
7. Confirm units, device classes, state classes, and recorder continuity.
8. Compare old and new results before removing the fixed implementation.
9. Calibrate one repeater using a multimeter.
10. Repeat for the remaining repeaters.

Every repeater migration must be verified before its previous entity
definition is removed. Verification must include entity-registry identity,
current state, availability, units, recorder history, dashboard references,
graphs, statistics, alerts, and automations.

During transition, a repeater using defaults must produce the same result as
the existing fixed calibration.

If entity replacement requires a temporary entity, use an explicit migration
sensor and move the stable entity ID only during a controlled maintenance
window. Do not update dashboards to temporary IDs.

### Historical Data

Recorder history must remain associated with the stable calibrated entity ID
where possible. Calibration events should be recorded as annotations or
maintenance events so historical changes can be interpreted correctly.

Template sensors calculate live calibrated values only. Changing a
calibration helper affects future template evaluations and does not rewrite
states already stored by Home Assistant Recorder.

Raw recorder history may be recalculated on demand using the calibration
selected for that repeater. On-demand recalculation must:

- Read the repeater's raw historical voltage.
- Resolve the explicitly selected calibration record and schema version.
- Apply the same validation and calibrated-voltage formula used for live
  values.
- Return unavailable for invalid raw samples or invalid calibration ranges.
- Produce a separate result series with provenance linking it to the raw
  source and calibration record.
- Leave raw and existing calibrated recorder history unchanged.

On-demand recalculated history is non-destructive. Recalculated results must
be stored separately from existing recorder states unless a recorder migration
is deliberately performed.

Permanently backfilling or rewriting recorder data is a separate data-migration
project that requires explicit approval, backup, validation, rollback
planning, and a documented mapping from raw samples to calibration records.
It is not part of ordinary helper changes or repeater migration.

### Rollback

Each migrated repeater must support rollback by restoring:

- Offset to `-0.816 V`
- Empty voltage to `3.000 V`
- Full voltage to `4.200 V`
- Profile to `18650 Li-ion`

Rollback must not require dashboard changes.

---

## Stretch Goals

### Calibration History

Store timestamped calibration events with old and new offsets, measurement
conditions, operator, and confidence.

### Maintenance History

Record inspections, firmware updates, enclosure work, antenna changes,
charging faults, and other node maintenance.

### Battery Passport Extensions

Record installation date, battery identifier, chemistry, rated capacity,
supplier, and retirement reason. Extend the dedicated Battery Passport rather
than creating a separate source of truth.

### Per-Node Notes

Provide structured and free-form notes for installation conditions, access
instructions, environmental exposure, and known issues.

### Battery Chemistry Library

Maintain versioned chemistry profiles with:

- Nominal voltage
- Safe minimum and maximum voltage
- Discharge curve
- Charging characteristics
- Temperature considerations
- Expected cycle life

---

## Terminology

### Raw Voltage

The unmodified voltage measurement received from a repeater and retained for
diagnostics and optional historical recalculation.

### Calibration Record

The versioned, per-repeater offset, voltage range, provenance, date, and
confidence used to derive calibrated voltage.

### Live Calibrated Voltage

The current template-sensor result calculated from the current raw state and
the repeater's currently selected calibration.

### Recorded Calibrated Voltage

A historical live-calibrated state already stored by Home Assistant Recorder.
Changing a helper does not rewrite it.

### Recalculated Historical Voltage

A non-destructive derived result calculated from raw recorder history and an
explicitly selected historical or current calibration record. It is stored
separately unless an approved recorder migration occurs.

### Battery Profile

A versioned definition of chemistry, voltage limits, and optionally a
discharge curve.

### Calibration Confidence

Confidence in the accuracy and provenance of a repeater's calibration.

### Analytics Confidence

Confidence in an analytic output based on sample count, history coverage,
data quality, and trend stability. It is independent of calibration
confidence.

### Battery Passport

The lifecycle record for a physical battery, its assignments, service,
observations, and replacement history.

---

## Acceptance Tests

### Entity Continuity

- Existing calibrated-voltage and battery-percentage entity IDs remain
  available where technically possible.
- Entity-registry IDs and unique IDs are verified before removing old
  definitions.
- Dashboards, automations, graphs, statistics, and alerts resolve the expected
  entities after migration.
- Recorder continuity is checked for every migrated repeater.

### Invalid Values

- Unknown, unavailable, null, empty, non-numeric, and non-finite raw states
  produce unavailable derived sensors.
- Known error sentinels and out-of-range raw or calibrated voltages produce
  unavailable derived sensors.
- Full voltage less than or equal to empty voltage produces unavailable
  derived sensors.
- Invalid inputs are never clamped into plausible battery percentages.
- Valid percentages below 0% or above 100% are constrained to 0–100% only
  after all validation succeeds.

### Restart Restoration

- Valid helper states restore without changing the calculated result.
- Invalid restored helper states make derived sensors unavailable.
- Missing or unsupported profile and schema versions produce a visible
  calibration-invalid diagnostic.
- Defaults are not silently substituted for invalid restored values.

### Recorder Behavior

- Changing a helper changes live calculations only.
- Existing recorder history remains unchanged after helper edits.
- On-demand recalculation reads raw history and writes results separately.
- Recalculated results include calibration and schema provenance.
- An approved backfill is tested on a backup and has a verified rollback.

### Repeater-by-Repeater Migration

- Default values reproduce the previous fixed calibration.
- Each repeater is validated independently before migration continues.
- Removing an old definition occurs only after entity, recorder, dashboard,
  automation, and graph checks pass.

---

## Phased Implementation Roadmap

### Phase 1 — Foundations

- Inventory existing entities and consumers.
- Define stable naming conventions.
- Enable Home Assistant packages.
- Create per-repeater calibration helpers.
- Reproduce the existing linear calculation with default values.
- Add strict validity checks.

### Phase 2 — Repeater-by-Repeater Migration

- Create one package per repeater.
- Preserve calibrated voltage and battery percentage entity IDs.
- Compare results against the existing implementation.
- Migrate and test one repeater at a time.
- Confirm dashboard, graph, statistic, alert, and automation continuity.

### Phase 3 — Guided Calibration

- Add measured-voltage helpers.
- Implement offset calculation scripts.
- Add review and confirmation steps.
- Record calibration date and confidence.
- Create calibration history entries.

### Phase 4 — Battery Profiles

- Add 18650 Li-ion, LiPo, LiFePO4, and Custom profiles.
- Introduce versioned piecewise discharge curves.
- Validate curve interpolation against measured batteries.
- Preserve the linear profile as a compatibility option.

### Phase 5 — Operational Analytics

- Add charge and discharge rates.
- Add charging detection.
- Add estimated runtime with confidence.
- Add battery health scoring.
- Detect calibration and replacement boundaries in trend data.

### Phase 6 — Battery Passport

- Define the passport schema and schema version.
- Create stable battery identifiers.
- Record repeater assignments and assignment history.
- Capture manufacturer, model, chemistry, rated capacity, and lifecycle dates.
- Link passports to calibration records without copying calibration values.
- Record service history, health observations, replacement reasons, and
  notes.

### Phase 7 — Deterministic Forecasting and Maintenance

- Add replacement forecasting.
- Add deterministic maintenance recommendations using documented thresholds.
- Add battery and calibration aging alerts.
- Integrate maintenance history and per-node notes.

### Phase 8 — Maintenance History

- Define an append-oriented maintenance-event schema.
- Record inspections, repairs, firmware work, charging faults, and enclosure
  work.
- Link maintenance events to repeaters and Battery Passports.
- Keep maintenance history separate from calibration records.

### Phase 9 — Governance and Hardening

- Document ownership and change procedures.
- Add configuration validation and regression tests.
- Review entity and recorder continuity.
- Version battery profiles and calibration schemas.
- Define backup, rollback, and audit procedures.

This document is the design specification for MeshCore NOC Battery
Intelligence. Implementation must preserve the separation of concerns:
repeaters own calibration, derived entities own calculations, and dashboards
own presentation.
