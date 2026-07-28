# MeshCore NOC v1.0 Existing-Service Live Test

Status: required before runtime adapter implementation

Date prepared: 2026-07-28

## Purpose

This procedure verifies the installed MeshCore Home Assistant integration using
only public Home Assistant surfaces. It does not modify MeshCore, import its
Python modules, access its config-entry internals, or communicate directly with
hardware.

The hard project constraint is:

> MeshCore NOC will not require modifications to the MeshCore Home Assistant
> integration.

The test determines whether the installed public `meshcore.execute_command`
service is sufficient for a small NOC adapter. Do not add runtime command code
until every required observation below has been captured.

## Safety boundary

- Use one non-critical managed test repeater.
- Start with read-only `clock`; do not test `clock sync`, `reboot`, or
  `clkreboot` until `clock` targeting and event behavior are understood.
- Do not paste a password into an issue, screenshot, log extract, diagnostic
  download, or committed file.
- Do not enable `record_to_console` for `send_login`; its event contains the
  full command string.
- Do not run overlapping commands or normal manual messages during the capture.
- A successful service call or `MSG_SENT` result is not a repeater response.

## Record installed facts

In Home Assistant:

1. Open **Settings > System > Repairs > three-dot menu > System information**
   and record the Home Assistant version.
2. Open **Settings > Devices & services > MeshCore**. Record the integration
   version shown in its overflow/about information, or record `not shown`.
3. Open the selected MeshCore config entry and record its entry title and
   transport type. Redact addresses if they identify a private site.
4. Open the selected repeater device and record:
   - Home Assistant device ID from the URL;
   - repeater name;
   - stable public-key prefix exposed by public entity/device attributes, if
     present;
   - the MeshCore config entry that owns it; and
   - source availability/freshness entities used by NOC.
5. In **Settings > Devices & services > MeshCore > Diagnostics**, download a
   diagnostic only if it is already redacted by the integration. Do not share
   passwords or private keys.

The meshcore-py version may not be visible through public HA surfaces. Record it
as `not publicly exposed` unless the integration diagnostics explicitly report
it. Do not inspect `hass.data`, site-packages, or private integration objects.

## Confirm the service contract

Open **Developer Tools > Actions** and select
`meshcore.execute_command`. Record:

- whether the action exists;
- the fields displayed;
- whether the UI offers a returned response;
- whether `command` is required;
- whether `entry_id` and `record_to_console` are available; and
- any validation error produced by an empty command.

For the audited 2.9.0 baseline, the expected public data schema is:

```yaml
command: "<meshcore-py command and arguments>"
entry_id: "<optional MeshCore config-entry ID>"
record_to_console: false
```

The audited schema has no separate `device_id`, contact, password, remote CLI
command, timeout, request ID, or cancellation fields. Those values, where
applicable, are positional content inside the `command` string.

## Open public event listeners

Before calling a service, open separate **Developer Tools > Events** listeners
for both event types:

```text
meshcore_cli_response
```

```text
meshcore_message
```

Start listening on each. Also open **Settings > System > Logs**, filter for
MeshCore, and note the time. Do not enable debug logging unless the resulting
capture can be reviewed and redacted safely.

Expected audited `meshcore_cli_response` fields:

```yaml
command: "<full execute_command string>"
response: "<normalized immediate SDK result or null>"
is_error: false
entry_id: "<requested entry ID or null>"
timestamp: 1785240000
```

This event mirrors the service result. For `send_cmd`, it is expected to
describe local send acceptance/error, not the remote CLI response.

Expected audited incoming direct `meshcore_message` fields:

```yaml
message: "<incoming text>"
sender_name: "<resolved contact name>"
pubkey_prefix: "<sender public-key prefix>"
receiver_name: "meshcore"
entity_id: "<contact message entity>"
domain: "meshcore"
timestamp: "<ISO timestamp>"
message_type: "direct"
hop_count: 0
snr: "<optional>"
```

This is a possible passive CLI-response observation channel. It has no request
ID, original command, or completion flag.

## Establish the exact target

Use the public-key prefix shown by the selected repeater's public HA registry or
entity data. Prefer at least 12 hexadecimal characters. Do not use only a
mutable display name when a stable prefix is available.

Confirm that NOC currently manages the same HA repeater device and that the
source entities belong to the same MeshCore config entry. Stop if the target is
ambiguous or the public-key prefix is not publicly available.

The audited 2.9.0 parser resolves the first positional `send_cmd` argument by
public-key prefix or exact contact name. `entry_id` selects the local MeshCore
companion/config entry; it does not select the remote repeater.

## Authentication probe

The audited public service exposes no typed login operation and no public login
state. The generic form is:

```yaml
action: meshcore.execute_command
data:
  entry_id: "<MeshCore config-entry ID>"
  command: >-
    send_login <repeater-public-key-prefix> "<temporary test password>"
  record_to_console: false
```

Only run this if the operator explicitly accepts entering the password into
Home Assistant Developer Tools and has verified that service-call tracing is
not persisting it. Clear the form afterward. Do not capture or publish the
service call.

Record only:

- call raised an error;
- call returned no response;
- call returned an immediate send result; or
- a separate public event proved login success.

The audited `execute_command` allow-list exposes asynchronous `send_login`, not
`send_login_sync`. Immediate send acceptance does not prove authentication.
If no public login-success evidence appears, authentication remains
unconfirmed and the NOC adapter remains blocked.

If the repeater is already authenticated through normal MeshCore operation, do
not assume that session persists; record the observation as session-dependent.

## Read-only `clock` probe

With both event listeners still running, invoke:

```yaml
action: meshcore.execute_command
data:
  entry_id: "<MeshCore config-entry ID>"
  command: >-
    send_cmd <repeater-public-key-prefix> "clock"
  record_to_console: true
```

Capture, with private identifiers redacted consistently:

1. action start and completion timestamps;
2. the returned service response, if the UI displays one;
3. the matching `meshcore_cli_response` event;
4. every `meshcore_message` direct event from the target for at least the
   conservative response window;
5. relevant MeshCore log lines;
6. source freshness/availability state before and after; and
7. whether unrelated incoming direct messages occurred.

Classify the result:

| Stage | Required evidence |
| --- | --- |
| A. Service accepted | HA action call completed without validation/service error |
| B. Handed to transport | Public service result explicitly indicates dispatch; otherwise unknown |
| C. Message confirmed sent | Public result explicitly represents `MSG_SENT`; record payload |
| D. CLI response received | A public `meshcore_message` direct event has the target prefix and plausible response text |
| E. Effect verified | Independent public state/telemetry proves the requested operational effect |

For `clock`, D may be observed passively, but correlation remains provisional:
the event lacks a request ID and completion marker. Do not calculate or expose
an exact clock offset until the message format, timestamp semantics, and
correlation are proven.

## Mutating-command test gate

Do not execute the following merely to complete this procedure:

- `clock sync`;
- `reboot`; or
- `clkreboot`.

They may be tested later only after the read-only probe proves exact targeting,
authentication behavior, cooldown expectations, service response semantics,
and source-state observation.

When explicitly approved for a controlled repeater, the generic service shapes
would be:

```yaml
command: >-
  send_cmd <repeater-public-key-prefix> "clock sync"
```

```yaml
command: >-
  send_cmd <repeater-public-key-prefix> "reboot"
```

```yaml
command: >-
  send_cmd <repeater-public-key-prefix> "clkreboot"
```

For reboot verification, capture pre-command availability/freshness, any stale
or unavailable transition, return to fresh/available, first new telemetry, and
elapsed recovery time. Absence of an offline transition is not failure by
itself. Mark `effect_verified` only when independent post-command evidence
supports a reboot/recovery; otherwise use `response_unavailable` or
`effect_pending`.

## Decision record

The runtime adapter is allowed only if the live capture confirms all of:

- installed service and response support;
- stable managed-repeater-to-contact targeting using public data;
- safe authentication without NOC reading or persisting MeshCore passwords;
- reliable distinction between service acceptance and `MSG_SENT`;
- public `meshcore_message` availability for passive response observation;
- conservative same-target single-flight and cooldown behavior can be layered
  in NOC without bypassing MeshCore;
- failure and unavailable-service behavior; and
- sufficient public source entities for reboot operational verification.

If authentication requires NOC to store/pass a repeater password, or if target
identity cannot be derived from public registry/entity data, the adapter must
not be implemented.

Even when allowed, the initial adapter must describe CLI replies as
`response_unavailable` unless an observed `meshcore_message` can be attributed
without ambiguity. It must never promote A, B, or C to D or E.
