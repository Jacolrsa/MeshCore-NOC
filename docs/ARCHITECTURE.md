# MeshCore NOC v4 Architecture

## Migration-first objective

MeshCore NOC v4 initially preserves the MeshCore NOC v3.1.1 dashboard's
appearance, behaviour, calculations, thresholds, and features as closely as
practical. The first objective is to convert the existing YAML solution into a
self-contained Home Assistant integration, not to redesign it.

The first usable release should retain:

- the overview dashboard layout and repeater cards;
- voltage and battery graphs;
- battery intelligence;
- calibration controls;
- freshness and offline status logic;
- alerts and health information; and
- the existing thresholds and calculations.

The first implementation may continue to depend on Mushroom, ApexCharts, and
card-mod. Removing these dependencies is a later phase and must not block the
first integration release.

## Ownership boundary

The MeshCore integration remains the source of truth for:

- MeshCore repeaters;
- repeater discovery;
- repeater source entities; and
- repeater identity and availability.

MeshCore NOC owns:

- selection of the MeshCore repeaters monitored by NOC;
- calibration and calibrated monitoring entities;
- battery intelligence;
- alerts;
- graph configuration;
- health status;
- statistics; and
- the NOC dashboard representation.

MeshCore NOC must not duplicate or replace MeshCore repeater management.

## Discovery and source association

MeshCore NOC reads repeater information from the existing MeshCore Home
Assistant integration. Users do not manually enter entity IDs. For each
repeater, NOC should automatically associate the available source entities and
metadata, including voltage, battery percentage, airtime utilisation, last
update or availability, repeater name, and a stable MeshCore identifier.

The exact entity-discovery mechanism will be defined during implementation.

## Adding repeaters

Repeaters discovered by MeshCore but not monitored by NOC appear as available
repeaters. The user can choose **Add to NOC**.

Adding a repeater will create or configure its calibration settings, calibrated
voltage, calibrated battery percentage, monitoring status, battery
intelligence, alerts, dashboard entry, health entities, and statistics
entities. This workflow must not require users to create helpers or template
sensors manually.

## Removing repeaters

### Remove from NOC

A user may stop monitoring a repeater while leaving it installed and managed
by MeshCore. This action removes or disables only NOC-owned monitoring
configuration and data for that repeater.

### Repeater removed from MeshCore

NOC offers permanent cleanup only when the repeater no longer exists in the
MeshCore integration. Offline, stale, unknown, or unavailable repeaters are
not removed repeaters.

After confirmation, permanent cleanup removes NOC-owned data and configuration
associated with the repeater. If the same repeater is later added to MeshCore,
NOC treats it as a new repeater and does not restore its old calibration.

## First usable milestone

The first reliable v4 workflow is:

```text
Install MeshCore NOC
        ↓
Add the MeshCore NOC integration
        ↓
NOC discovers repeaters from the MeshCore integration
        ↓
User chooses which repeaters to add
        ↓
The familiar v3-style dashboard is generated and maintained
```

No visual redesign or unrelated advanced feature should precede a reliable
version of this workflow.

## v4.0.0-alpha1 foundation

Alpha1 implements only UI configuration, source discovery, managed-repeater
selection, persistence, coordination, and diagnostics. It creates no NOC
sensors, binary sensors, numbers, buttons, per-repeater NOC devices, alerts,
calibration controls, calculations, or dashboards.

### Discovery assumptions

Discovery starts with loaded `meshcore` config entries and reads Home
Assistant's device and entity registries without modifying them. A candidate
must have:

- a config-entry relationship to MeshCore;
- a MeshCore-owned device identifier.

Entities whose registry platform is `meshcore` and whose config-entry and
device relationships match the candidate are used for source mapping. A
candidate with no linked source entities remains discoverable and reports all
expected roles as missing.

The MeshCore-owned device identifier is the stable internal repeater ID.
Friendly names are display metadata only. Device classes and units are
preferred when mapping source roles. Entity ID, unique ID, original name, and
translation key tokens are guarded compatibility fallbacks for optional role
mapping only; they are never identity.

The current MeshCore registry contract is not available in this repository.
Consequently, live validation must confirm that repeater devices expose
`("meshcore", stable_id)` identifiers, MeshCore platform entities, and
config-entry/device relationships as assumed. Devices without a MeshCore
identifier are skipped with a diagnostic warning rather than assigned an
invented identity. Missing optional sources do not exclude a repeater.
Unavailable, unknown, stale, or offline source states do not remove a
registry-owned repeater.

### Stored config-entry format

Alpha1 uses config flow schema version `1.1`.

```json
{
  "data": {
    "meshcore_config_entry_ids": ["<Home Assistant config entry ID>"]
  },
  "options": {
    "managed_repeater_ids": ["<stable MeshCore repeater ID>"]
  }
}
```

The source config-entry IDs provide setup-time provenance. The managed stable
IDs are stored in options so the options flow can replace the selection without
editing MeshCore devices or entities. Home Assistant persists config entry
options across restart and reload.

### Alpha1 Definition of Done

- Home Assistant recognizes MeshCore NOC as a single-instance config-flow
  integration.
- Setup aborts with a translated explanation when MeshCore is not configured.
- Registry-owned repeaters are discovered without manual entity IDs.
- Users select managed repeaters by display label while stable IDs are stored.
- Options can replace the managed selection.
- Restart and reload preserve the selection through config entry options.
- Diagnostics report source mappings, missing roles, and discovery warnings.
- No monitoring entities, NOC devices, calculations, or dashboard changes are
  created.
- Unload changes no MeshCore registry record.

### Known alpha1 limitations

- The discovery contract requires validation against a live MeshCore Home
  Assistant registry.
- Alpha1 performs discovery at setup, options, explicit coordinator refresh,
  and config-entry load. It does not yet subscribe to registry events.
- Entity role matching is intentionally conservative and may leave optional
  mappings missing.
- Selection controls use one standard multi-select. Selected items are managed;
  unselected discovered items are available.
- The supported development baseline is Home Assistant 2026.6 or newer. Home
  Assistant manifests do not define a custom-integration minimum-version key,
  so this baseline is documented rather than expressed as a nonstandard
  manifest field.

## v4.0.0-alpha1.1 discovery hardening

Live Home Assistant validation confirmed that the MeshCore registry exposes
both repeaters and clients. Alpha1.1 keeps both device types discoverable and
selectable. The existing `managed_repeater_ids` options key is intentionally
unchanged; despite its historical name, it may contain stable IDs for selected
repeaters or clients. Existing alpha1 config entries need no migration.

Device type is runtime metadata with three values: `repeater`, `client`, or
`unknown`. Classification uses this order:

1. structured MeshCore device registry metadata, including model, model ID,
   manufacturer, and MeshCore identifiers;
2. MeshCore entity registry unique IDs and translation keys; and
3. the mutable device display name as a documented low-confidence fallback.

Exact `repeater`, `relay`, `client`, `companion`, and `handset` tokens are used.
Conflicting or absent evidence produces `unknown` rather than an invented
classification. Type affects presentation only and never changes a stable ID.
The standard multi-select displays prefixed labels such as
`📡 Repeater • Promicro` and `📱 Client • Jaco`.

Source mapping ranks exact registry metadata rather than accepting the first
name match. Translation keys and unique-ID role matches outrank device class,
units, original names, and entity-ID fallback matching. Disabled entities are
deprioritized. A warning is emitted only when the strongest candidates remain
equally ranked; lower-ranked alternatives do not produce repetitive duplicate
warnings.

Diagnostics include device type, classification method, mapping method,
confidence score and band, linked source entity count, and totals for
repeaters, clients, and unknown devices. Missing roles are reported separately
and do not generate redundant warnings.

## v4.0.0-alpha2 managed-device monitoring

Alpha2 instantiates only the first stable ID selected by Alpha1. Setup reuses
Alpha1's registry discovery result and creates one `DataUpdateCoordinator` for
that managed device. Voltage, battery, health, and freshness entities all read
the same immutable calculated snapshot. This keeps calculations consistent and
allows Alpha3 to scale by creating another coordinator per selected stable ID.

The production defaults are embedded for this validation release: a `-0.816 V`
offset, `3.000 V` empty voltage, and `4.200 V` full voltage. Fresh, Aging,
Stale, and Offline begin at ages of 0, 4,500, 7,200, and 10,800 seconds.
Calibration configuration remains deliberately out of scope.

The integration registers a `MeshCore NOC` service device with a child
`📡 ProMicro Repeater` device. All Alpha2 entities belong to the child device.

### Branding

Home Assistant 2026.3 and newer can load custom-integration artwork from
`custom_components/meshcore_noc/brand/`. The integration ships light and dark
icons and logos at 1× and 2× there. These assets use the independent MeshCore
NOC network-node identity and are generated by
`scripts/generate_branding_package.ps1`; no upstream visual artwork is used.

## v4.0.0-alpha2.1 update behaviour

Alpha2.1 preserves Alpha2's four unique IDs and single managed-device
coordinator. Each entity now uses a short device-scoped display name while an
explicit proposed entity ID preserves the established ID on a new installation.
The unchanged unique ID remains authoritative for existing registry entries.

The coordinator subscribes once to the mapped MeshCore voltage entity before
its initial refresh. Source state changes request an immediate debounced
coordinator refresh, so voltage, battery, health, and freshness update from one
calculated snapshot. The one-minute scheduled refresh remains only to advance
freshness when no source event occurs. Successful unload removes the source
listener explicitly.

## v4.0.0-alpha2.2 presentation

Alpha2.2 adds only repository documentation and local Home Assistant branding.
It preserves Alpha2.1 discovery, entity registration, coordinator behavior,
configuration, diagnostics, unique IDs, and device identifiers.

## v4.0.0-alpha3 managed repeaters

Alpha3 creates one existing coordinator type for every selected stable ID found
in the immutable discovery result. Each coordinator retains its own source
listener and one-minute freshness refresh, and its voltage, battery, health,
and freshness entities continue to consume one calculated snapshot.

The original Alpha2 unique IDs and proposed entity IDs remain assigned to the
device that already owns them in the entity and device registries. On a new
installation, the first selected stable ID receives that legacy ProMicro
identity. Additional repeaters use their MeshCore stable ID in unique IDs and
their normalized display name only for presentation and proposed entity IDs.
Selection reordering therefore cannot transfer existing Alpha2 entities to a
different managed device.
