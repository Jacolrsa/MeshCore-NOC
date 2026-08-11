# MeshCore NOC v1.1 Beta 5 — Repeater management

Beta 5 keeps the Beta 4 Mission Control layout: the fleet dashboard monitors,
while each repeater detail view is the management surface.

## Persistent settings

Settings are stored per NOC stable ID in Home Assistant private persistent
storage and survive Core restarts, integration reloads, and dashboard reloads.
Calibration, battery thresholds, Last Seen thresholds, clock thresholds, and
the dashboard display name are returned to an administrator through a narrow
integration websocket API. Changes are only persisted after **Save**.

Repeater passwords use the same stable-ID store but remain behind a secret
boundary. The API reports only whether a password is configured. It never
returns the password, places it in an entity or diagnostics payload, or writes
it to a log. Changing a password always requires a new value; the existing
value is never displayed.

The dashboard reports only whether a password is configured and the UTC time at
which it was last changed. Password storage is complete, but automatic command
authentication remains disabled until MeshCore exposes a typed authentication
operation that does not place the password in command text, service traces,
events, or logs.

## Validation

- Voltage offset: −2.0 V to +2.0 V.
- Empty and full voltage: 2.0 V to 6.0 V, with empty below full.
- Battery critical: below battery warning, both within 0–100%.
- Fresh, aging, stale, and offline ages: ordered from 60 seconds to 7 days.
- Clock warning: below clock critical, up to 24 hours.
- Dashboard display name: optional, up to 80 characters.

Invalid input is rejected before storage and shown on the repeater detail page.
**Cancel** restores saved values. **Reset Defaults** loads defaults into the
form and still requires **Save**, preventing accidental persistence.

## Preserved behavior

Entity IDs, unique IDs, config-entry identities, managed discovery, service
names and schemas, clock execution and correlation, fleet scheduling, and the
Beta 4 graph layout remain unchanged.
