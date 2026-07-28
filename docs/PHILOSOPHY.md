# MeshCore NOC v4 Philosophy

MeshCore NOC v4 is migration-first. Its earliest goal is a reliable Home
Assistant integration that preserves the familiar v3.1.1 experience, not a
visual redesign.

The project follows four principles:

1. **Preserve proven behaviour.** Existing layouts, calculations, thresholds,
   controls, alerts, health information, graphs, and battery intelligence form
   the functional baseline.
2. **Respect ownership.** MeshCore owns repeater discovery, identity,
   availability, and source entities. NOC owns opt-in monitoring and the
   derived NOC experience.
3. **Reduce manual configuration.** Users select discovered repeaters; they do
   not copy YAML packages, create helpers, or type entity IDs.
4. **Migrate safely.** v3 remains operational until v4 is reliable and a
   deliberate migration step is ready.

Dependency reduction is valuable but secondary to migration fidelity. The
initial integration may use Mushroom, ApexCharts, and card-mod while the core
installation, discovery, selection, and dashboard workflow is stabilized.
