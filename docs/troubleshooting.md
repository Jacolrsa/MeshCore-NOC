# Troubleshooting

## Integration is not found

Confirm the path is exactly
`/config/custom_components/meshcore_noc/manifest.json`, then perform a full Home
Assistant restart. Check **Settings → System → Logs** for manifest or import
errors.

## Frontend looks unchanged after an update

MeshCore NOC uses a bundled local JavaScript module whose URL is cache-busted by
the integration version. After a HACS redownload or manual copy:

1. restart Home Assistant fully;
2. confirm the loaded MeshCore NOC version changed; and
3. hard-refresh the browser if the previous dashboard bundle is still visible.

## Graph briefly goes blank or says Loading repeatedly

This behaviour was fixed in 1.1.0. Recorder refresh now runs in the background
while the last good graph remains visible. A temporary refresh error also keeps
the last good graph.

If a 1.1.0 graph still blanks repeatedly, confirm the frontend bundle actually
loaded 1.1.0 and inspect the browser/Home Assistant logs for Recorder API errors.

Recorder is required for historical data but not for current voltage/battery
values.

## Graph has a gap

A gap is intentional when Recorder contains unknown/unavailable/invalid data.
1.1.0 also breaks the line across a large instantaneous value change that looks
like a calibration/Recorder discontinuity rather than a physical battery
transition. This avoids drawing a misleading vertical voltage event.

## Clock check times out on routed repeaters

Clock checks require the saved repeater administrator password. In 1.1.0 the
login and `clock` command use MeshCore's `suggested_timeout` from the actual
route, so routed nodes receive a longer valid response window than direct nodes.

If a routed repeater still times out:

- verify it is reachable in the upstream MeshCore integration;
- verify the saved administrator password;
- retry after route/path information has refreshed; and
- compare with a direct repeater to separate radio reachability from NOC logic.

## Clock check works but offset looks slightly different between checks

Clock offset is latency compensated using approximately half of the measured
clock-command RTT. Mesh radio paths are not perfectly symmetric, so small
variation between checks is normal. The default sync success window is ±30
seconds.

## Sync says no change was required

This is expected when the authenticated, latency-corrected pre-check is already
within ±30 seconds. 1.1.0 deliberately avoids rebooting or writing an already
synchronised repeater.

## Automatic sync does not start

Automatic sync is disabled by default. When enabled, an unattended run will not
start if any managed addressable repeater is missing its saved administrator
password. Configure passwords from each repeater detail page first.

## Branding is missing

Local custom-integration branding requires Home Assistant 2026.3 or newer.
Confirm all eight PNGs are in `custom_components/meshcore_noc/brand`, restart,
and refresh the browser/app cache. Follow the
[branding investigation](branding-investigation.md) if necessary.

## Managed repeater or entities are missing

Confirm the upstream MeshCore integration is loaded and the source device exists.
Open MeshCore NOC options and verify the intended device is selected. NOC owns
only its derived entities and does not recreate an upstream MeshCore device that
is absent from discovery.

## Values differ from raw MeshCore telemetry

Inspect entity attributes before comparing values. Calibrated voltage uses the
per-repeater configured offset and battery percentage maps the configured empty
and full voltages linearly to 0–100%. Freshness uses source update age and
availability rather than the time the dashboard was opened.

## Reporting

Download diagnostics, redact sensitive context, capture relevant Home Assistant
log lines and use the repository bug-report form. Never publish repeater
passwords, private node IDs, precise locations or unreviewed diagnostics.
