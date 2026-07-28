# MeshCore NOC v4 Migration

MeshCore NOC v3.1.1 remains a separate maintenance line. MeshCore NOC v4.0.0
is the current stable production release.
The initial v4 phases do not move, rename, delete, or modify the live dashboard,
YAML packages, Home Assistant configuration, or other v3 implementation files.

Migration is deliberately incremental:

1. Document v3 behaviour, calculations, thresholds, dependencies, and entity
   relationships.
2. Scaffold the Home Assistant integration without changing the live v3
   solution.
3. Reproduce repeater discovery, selection, calibration, monitoring, battery
   intelligence, alerts, health, statistics, and dashboard generation.
4. Validate v4 against the existing v3.1.1 behaviour and appearance.
5. Define an explicit, reviewed migration procedure before moving or retiring
   any legacy file.

Until that procedure is approved and proven, v3 remains the production
implementation and its live files stay in their current locations.
