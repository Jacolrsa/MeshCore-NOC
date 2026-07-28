# MeshCore NOC v4 Development

## Worktree and branch safety

- MeshCore NOC v4.0.0 on `main` is the stable production implementation.
- The original `C:\Projects\MeshCore-NOC` worktree remains dedicated to v3
  maintenance.
- All v4 work takes place in the separate
  `C:\Projects\MeshCore-NOC-v4` worktree.
- Future feature branches may be created from `v4-development`.
- Do not develop v4 directly on `main` or merge into `main` without explicit
  instruction.

## Change discipline

Changes should be small, reviewable, and limited to the intended migration
phase. Run validation and tests before every commit. Do not commit generated
files, caches, secrets, credentials, Home Assistant runtime data, test output,
or frontend build output.

The initial preparation phase contains documentation and empty component,
frontend, test, and legacy scaffolding only. Python integration code and
frontend implementation begin in later, separately reviewed changes.

## Alpha1 validation

The alpha1 test suite uses `pytest-homeassistant-custom-component` and Home
Assistant's `hass` fixture. Run it in a supported Home Assistant development
environment:

```text
pytest -p no:cacheprovider
```

The config-flow and registry lifecycle tests require the Home Assistant test
framework. JSON parsing, Python syntax compilation, translation-key comparison,
and whitespace validation can run without that framework. Validation must not
generate or commit bytecode, pytest caches, Home Assistant runtime data, or
secrets.

Alpha1.1 tests additionally cover repeater/client classification, display-label
prefixes, stable-ID preservation, exact role ranking over generic duplicate
candidates, and diagnostic classification totals.
