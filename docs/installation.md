# MeshCore NOC 1.1 installation and validation

## Prerequisites

- Home Assistant with a working upstream MeshCore integration.
- Home Assistant 2026.3 or newer for repository-local custom-integration branding.
- Home Assistant Recorder if historical graphs are required.
- A current Home Assistant backup.
- Repeater administrator passwords for clock checks/synchronisation.

## HACS custom-repository upgrade

If MeshCore NOC is already installed through HACS as a custom repository:

1. Open **HACS → MeshCore NOC**.
2. Choose **Redownload** and select the required release.
3. Wait for HACS to replace the integration files.
4. Perform a **full Home Assistant restart**. A config-entry reload alone does
   not reliably reload Python modules, the manifest or the frontend cache-bust
   version.
5. Hard-refresh the browser only if the old dashboard bundle remains cached.

Keep the existing MeshCore NOC config entry during a normal upgrade.

## Manual installation or upgrade

1. Back up Home Assistant.
2. Copy the complete `custom_components/meshcore_noc` directory from the release
   into `/config/custom_components/meshcore_noc`.
3. Confirm at least `manifest.json`, `__init__.py`, `clock.py`, `management.py`,
   `fleet_clock.py`, `fleet_sync.py`, `frontend/`, translations and `brand/` are
   present.
4. Restart Home Assistant fully.
5. For a new install, add **MeshCore NOC** under **Settings → Devices & services**
   and select the MeshCore devices to manage.
6. For an upgrade, keep the existing entry so stable IDs, entity identities and
   per-repeater settings remain associated with the same devices.

## Validate 1.1.0

1. Confirm **MeshCore NOC** loads without setup/repair errors and the loaded
   version is `1.1.0`.
2. Open Mission Control and confirm all selected managed repeaters appear.
3. Confirm fleet row colours reflect the worst current health/freshness, battery
   or clock condition.
4. Confirm each managed repeater has calibrated voltage, battery, health,
   freshness, clock offset/status and Check Clock control.
5. Open one repeater detail page, save its administrator password and run
   **Check this repeater**.
6. Test one direct and one routed repeater. Routed nodes may take longer because
   NOC honours MeshCore's route `suggested_timeout`.
7. Run **Check All** and confirm the run remains serialized.
8. Run **Sync All** once manually. Repeaters already within ±30 seconds should
   report that no reboot/clock write was required.
9. Leave Mission Control open for several minutes. Recorder refresh should
   update the graph without replacing it with a blank Loading state.
10. Test graph ranges and hover/legend controls.
11. Download diagnostics and review **Settings → System → Logs** for
   `meshcore_noc` errors.

Enable automatic synchronisation only after all managed addressable repeaters
have saved administrator passwords and the manual fleet test has completed
successfully.

See [v1.1 release notes](V1_1_RELEASE.md) and
[Troubleshooting](troubleshooting.md).
