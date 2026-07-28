# Troubleshooting

## Integration is not found

Confirm the path is exactly
`/config/custom_components/meshcore_noc/manifest.json`, then restart Home
Assistant. Check logs for manifest or import errors.

## Branding is missing

Local custom-integration branding requires Home Assistant 2026.3 or newer.
Confirm all eight PNGs are in `custom_components/meshcore_noc/brand`, restart,
and refresh the browser or companion-app cache. Follow the
[branding API investigation](branding-investigation.md) to distinguish a Core
discovery problem from a frontend problem.

## ProMicro device or entities are missing

Confirm the upstream MeshCore integration is loaded and its source entities
are available. Open MeshCore NOC options and verify the intended repeaters are
selected. Alpha3 creates one managed device and four entities for every
selected repeater found during discovery.

## Values differ

Inspect entity attributes before comparing timestamps or rounded values.
Calibrated voltage uses `raw - 0.816 V`; battery maps calibrated
`3.000–4.200 V` to `0–100%`. Freshness uses the last source update and source
availability, not the time the dashboard was opened.

## Reporting

Download diagnostics, redact any remaining sensitive context, capture the
relevant Home Assistant log lines, and use the repository bug report form.
