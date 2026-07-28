# Alpha3 installation and live validation

## Prerequisites

- Home Assistant 2026.3 or newer for repository-local branding.
- A working upstream MeshCore integration with repeater telemetry.
- A current Home Assistant backup.

## Upgrade or install

1. Copy the complete repository folder
   `custom_components/meshcore_noc` to
   `/config/custom_components/meshcore_noc`.
2. Confirm that `manifest.json`, `__init__.py`, `config_flow.py`, `sensor.py`,
   `binary_sensor.py`, `diagnostics.py`, translations, and `brand/` are present.
3. Restart Home Assistant. A config-entry reload alone does not reload Python
   module or manifest changes reliably.
4. For a new install, add **MeshCore NOC** under **Settings → Devices &
   services**, select the upstream MeshCore entry, and select the repeater.
5. For an Alpha1 or Alpha2 upgrade, keep the existing entry. Do not remove and
   re-add it; the stored selection and existing ProMicro entity identities
   should be preserved.

## Validate

1. Confirm **MeshCore NOC** loads without a repair or setup error.
2. Open its device page and confirm **MeshCore NOC**, **ProMicro Repeater**, and
   one managed device for every additional selected repeater appear.
3. Confirm each managed repeater has voltage, battery, health, and freshness
   entities. Confirm the original ProMicro entity IDs listed in the README are
   unchanged.
4. Compare calibrated voltage with the production dashboard. It should equal
   raw voltage minus `0.816 V`, rounded to three decimals.
5. Compare battery percentage. It maps calibrated `3.000–4.200 V` to `0–100%`.
6. Check the freshness entity and its attributes against the source entity's
   age: Fresh ≤75 min, Aging ≤120 min, Stale ≤180 min, Offline afterward.
7. Check health: Unknown without a battery value; Poor for Offline or battery
   below 20%; Fair for Stale or below 40%; Good for Aging or below 80%;
   otherwise Excellent.
8. Download diagnostics from the integration menu and confirm it succeeds.
9. Review **Settings → System → Logs** for `meshcore_noc` errors.

If a post-restart entity remains stale, reload MeshCore NOC once. Removal and
re-adding is a last resort because it complicates upgrade validation.
