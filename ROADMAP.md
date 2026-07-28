# MeshCore NOC Roadmap

MeshCore NOC v1.0.0 is the current stable release. The roadmap is directional;
planned work is not part of the stable release and has no assigned dates.

| Phase | Status | Focus |
| --- | --- | --- |
| A — Foundation | Released in 1.0.0 | Discovery, managed devices, calibrated telemetry, health, freshness, dashboard, update channels |
| B — Professional UI | Ongoing | TV optimisation, no-scroll Mission Control, card and chart hierarchy, detail popups |
| C — Intelligence | Planned | Prediction, charging, solar, degradation, smart alerts, trends |
| D — Network Operations | Planned | Topology, maps, link quality, coverage, history, fleet summaries |
| E — Version 1.0 Readiness | Released | API stability, tests, docs, translations, installation and migration |

See [MH-102 — Product Roadmap](docs/MH-102_Roadmap.md) for implemented scope,
planned capabilities, and roadmap guardrails.

## v1.0 Operational Intelligence

Clock Intelligence is implemented in `1.0.0`: manual
read-only clock checks for managed repeaters, signed offset and status
diagnostics, public Home Assistant event correlation, timeout, cooldown, and
bounded in-memory history. Clock sync, reboot, automation, and dashboard
controls remain future phases.

See [the operational-intelligence roadmap](docs/V4_1_ROADMAP.md) for the ordered implementation
plan.
