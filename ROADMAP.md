# MeshCore NOC Roadmap

MeshCore NOC `1.1.0` is the current stable release. The roadmap is directional;
planned work is not part of the stable release and has no assigned dates.

| Phase | Status | Focus |
| --- | --- | --- |
| A — Foundation | Released in 1.0.0 | Discovery, managed devices, calibrated telemetry, health, freshness, dashboard, update channels |
| B — Professional UI | Advanced in 1.1.0 | Mission Control hierarchy, fleet severity, detail management, interactive Recorder graph |
| C — Clock Operations | Released in 1.1.0 | Password-authenticated checks, route-aware timing, latency-aware sync, companion/replay recovery, automation |
| D — Intelligence | Planned | Prediction, charging, solar, degradation, smart alerts, trends |
| E — Network Operations | Planned | Topology, maps, link quality, coverage, route visibility, fleet summaries |

## Released in 1.1.0

- Authenticated individual and fleet clock checks.
- MeshCore route `suggested_timeout` handling for direct and multi-hop nodes.
- RTT-compensated clock measurement.
- Home Assistant UTC clock synchronisation with latency compensation.
- No-write/no-reboot result for repeaters already within ±30 seconds.
- Companion future-`lastmod` repair and repeater anti-replay recovery.
- Automatic checks and password-guarded automatic synchronisation.
- Persistent per-repeater calibration, thresholds, display name and private
  administrator-password storage.
- Fleet severity colours derived from health/freshness, battery and clock state.
- Stable background-refresh Recorder graph with 6 h / 24 h / 7 d / 30 d ranges,
  time labels, crosshair values and series controls.

## Next priorities

The next stable feature work should avoid destabilising the 1.1 clock workflow.
Likely areas are richer battery/solar intelligence, route/topology visibility and
further Mission Control graph/telemetry refinement.

See [v1.1 release notes](docs/V1_1_RELEASE.md) and
[MH-102 — Product Roadmap](docs/MH-102_Roadmap.md).
