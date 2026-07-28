# Contributing to MeshCore NOC

Thank you for helping make MeshCore monitoring safer and more useful. MeshCore
NOC is a Home Assistant custom integration that converts selected upstream
MeshCore telemetry into managed devices, calibrated measurements, operational
status, a generated Mission Control dashboard, and controlled update channels.

The project has a stable v4 release. Small, evidence-based, backwards-compatible changes
are especially valuable.

## Before you start

- Search existing issues and documentation.
- For a bug, gather exact versions, reproduction steps, relevant log lines, and
  redacted diagnostics.
- For a larger feature or architecture change, open an issue before investing
  in implementation.
- Never include credentials, private node IDs, precise private locations, or
  unredacted diagnostics.

Use the repository’s bug and feature request forms where possible.

## Development setup

Clone the repository and work from the branch appropriate to the change:

```sh
git clone https://github.com/Jacolrsa/MeshCore-NOC.git
cd MeshCore-NOC
git switch v4-development
```

The repository does not currently include a Python dependency lock or setup
script. Use an isolated Python environment with a compatible Home Assistant
development installation, `pytest-homeassistant-custom-component`, Pytest,
Ruff, Pillow for branding validation, and the other packages imported by the
tests. Node.js is required only for the standalone frontend test.

Do not commit virtual environments, caches, Home Assistant runtime data,
secrets, or generated test output.

## Branch workflow

- `main` is the stable v4 release line.
- `v4-development` is the active v4 development line.
- `v3-battery-intelligence` is the separate v3 production/maintenance line.
- Do not modify or merge across those lines unless the issue explicitly calls
  for it.
- Do not develop directly on `main`.
- Create a focused branch from the intended base when submitting a pull
  request.
- Rebase or merge only with maintainer guidance; never rewrite another
  contributor’s published work.

## Architecture and compatibility

Read [MH-103 — Architecture](docs/MH-103_Architecture.md) before changing
runtime behaviour.

MeshCore owns raw identity, discovery, telemetry, and availability. MeshCore
NOC owns opt-in managed devices and derived operational behaviour. Changes must
respect that boundary.

Preserve:

- stable MeshCore IDs stored in config-entry options;
- managed-device identifiers;
- entity unique IDs and entity IDs, including the original ProMicro identity;
- existing config entries and upgrade behaviour;
- safe unload and deselection cleanup; and
- the separation between managed telemetry and updater coordinators.

Do not silently break an existing Home Assistant installation. Any unavoidable
migration needs an explicit migration implementation, tests, documentation,
rollback guidance, and maintainer review.

## Documentation expectations

- Update public documentation whenever behaviour, requirements, or operator
  workflow changes.
- Describe only implemented functionality as current.
- Label proposals and roadmap items as planned.
- Keep installation and update instructions executable and consistent with the
  repository.
- Use `MeshCore`, `MeshCore NOC`, `Home Assistant`, and `Lovelace`
  consistently.
- Add screenshots only from a redacted live environment; do not present mock
  UI as product evidence.
- Keep Markdown links relative and working.

## UI contributions

Follow:

- [MH-100 — UI Specification](docs/MH-100_UI_Specification.md); and
- [MH-101 — Design System](docs/MH-101_Design_System.md).

UI changes must remain TV-readable, responsive, keyboard accessible, and
truthful about Unknown data. Preserve the generated dashboard strategy and do
not add external fonts, scripts, raster dependencies, or unsupported custom
cards without prior agreement. Include or update frontend tests for dashboard
logic.

## Code quality

- Keep changes limited to one purpose.
- Follow the existing async Home Assistant patterns.
- Prefer immutable data and explicit ownership checks.
- Do not broadly suppress exceptions.
- Add comments for safety boundaries and non-obvious compatibility behaviour.
- Avoid unrelated formatting churn.
- Do not bump a version or edit the changelog unless the change is intended for
  a release.

## Testing

Run the checks supported by the repository:

```sh
python scripts/validate_branding.py
python -m compileall -q custom_components/meshcore_noc
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
pytest -q
git diff --check
```

When Node.js is available:

```sh
node --test tests/frontend/test_dashboard.js
```

Run targeted tests during development and the full suite before requesting
review. Runtime changes also require live Home Assistant validation appropriate
to their risk. If your local environment cannot run a check, say exactly why in
the pull request.

## Pull-request checklist

- [ ] The change has one clear purpose.
- [ ] Current behaviour and ownership boundaries were inspected first.
- [ ] Existing config entries, stable device identifiers, and entity IDs remain
      compatible.
- [ ] Tests reproduce the issue or protect the new behaviour.
- [ ] Python, frontend, formatting, lint, branding, and whitespace checks pass
      where applicable.
- [ ] Documentation and changelog are accurate for the intended release.
- [ ] Planned functionality is not presented as available.
- [ ] No secrets or sensitive MeshCore data are included.
- [ ] Risk and rollback are described.

## Reporting issues

A useful bug report includes:

- MeshCore NOC, Home Assistant, and upstream MeshCore versions;
- selected update channel where relevant;
- expected and actual behaviour;
- minimal reproduction steps;
- relevant log lines;
- redacted diagnostics; and
- whether Home Assistant was restarted after installation.

For security-sensitive reports, do not open a public issue with exploit details
or private data. Follow [SECURITY.md](SECURITY.md) and contact the repository
maintainers privately through an appropriate GitHub mechanism.

## Conduct

Participation in this project is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md).
