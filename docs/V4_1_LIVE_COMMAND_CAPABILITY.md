# MeshCore NOC v1.0 Live Command Capability Report

Status: live verification blocked; source verification complete

Investigation date: 2026-07-28

Release branch: `main`

## Decision

No MeshCore NOC runtime proof of concept is implemented by this investigation.
The supplied environment does not expose the actual Home Assistant installation,
and the audited MeshCore HA 2.9.0 interface does not provide a correlated remote
CLI response contract. Sending `clock` without being able to attribute and
complete its response would not meet the proof-of-concept safety requirements.

Project policy now prohibits requiring MeshCore integration changes. The next
step is the public Home Assistant live-test procedure in
`V4_1_EXISTING_SERVICE_LIVE_TEST.md`, using the existing
`meshcore.execute_command`, `meshcore_cli_response`, `meshcore_message`, public
entities, and registry data only. NOC must not import MeshCore integration
internals or communicate with hardware directly.

## Evidence method and boundaries

The investigation used read-only checks:

1. enumerated Git worktrees, local processes, Windows services, Docker
   containers, common Home Assistant configuration paths, and repository
   deployment references;
2. checked for configured Home Assistant URL/token and SSH targets without
   printing secret values;
3. attempted DNS resolution and an HTTP HEAD request for
   `homeassistant.local:8123`;
4. inspected the locally installed Python distribution metadata and source;
5. compared those findings with the previously captured upstream sources.

Results:

- no Home Assistant process, service, container, Python distribution, config
  directory, URL/token, or SSH target was found;
- Docker was not running;
- `homeassistant.local` did not resolve;
- the in-app browser connection was unavailable, so it supplied no live
  authenticated Home Assistant evidence;
- the local host has a standalone `meshcore` Python distribution, but there is
  no evidence that Home Assistant uses that interpreter or package.

Consequently, this report distinguishes `confirmed on the local host`,
`confirmed in audited source`, and `not verified in the actual HA instance`.
Nothing confirmed only from source is presented as a live installed capability.

## Installed versions

| Component | Result | Exact evidence |
| --- | --- | --- |
| MeshCore Home Assistant integration | **Unknown / not live-verified** | No HA installation or API was reachable; no live `custom_components/meshcore/manifest.json` was found. |
| MeshCore integration source path | **Unknown / not live-verified** | No live HA config directory or container was found. |
| `meshcore-py` used by Home Assistant | **Unknown / not live-verified** | HA's Python environment was not available. |
| Standalone host `meshcore-py` | **2.3.7** | `python -m pip show -f meshcore` reported version 2.3.7 at `C:\Users\Jaco\AppData\Local\Programs\Python\Python313\Lib\site-packages`. |
| Audited MeshCore HA baseline | **2.9.0** | Captured `custom_components/meshcore/manifest.json`, repository commit `1ee608a3f065d653ae0a69b6bc9b716ed5ef4610`. |
| Audited meshcore-py source | Requirement baseline **>=2.3.7** | MeshCore HA 2.9.0 manifest requirement; captured SDK repository commit `c487efbe187f4b000020afdfc0349c4cdf503c5a`. |

The standalone host package is useful corroborating evidence for SDK shape, but
it is not the answer to “which meshcore-py does Home Assistant run.”

## Actual services and schemas

### Live environment

The actual service registry and schemas are **not verified**. In particular,
this investigation cannot confirm that `meshcore.execute_command` is registered
in the user's running Home Assistant.

The required live evidence is a Home Assistant service-registry/API result plus
the installed integration's `services.yaml` and runtime manifest.

### Audited MeshCore HA 2.9.0 baseline

The captured 2.9.0 source defines these command-relevant services:

| Service | Schema | Response mode | Exact evidence |
| --- | --- | --- | --- |
| `meshcore.execute_command` | required `command: string`; optional `entry_id: string`; optional `record_to_console: boolean` | `SupportsResponse.OPTIONAL` | `services.py` `EXECUTE_COMMAND_SCHEMA` and registration; `services.yaml` |
| `meshcore.execute_command_ui` | optional `entry_id: string`; optional `record_to_console: boolean` | `SupportsResponse.OPTIONAL` | `services.py` `EXECUTE_COMMAND_UI_SCHEMA` and registration; `services.yaml` |
| `meshcore.cli_console_clear` | optional `entry_id: string` | no command response | `services.yaml`; `services.py` registration |

Other services in that source include messaging, contact, channel, trace, and
discovery helpers. None is a typed remote CLI request/response service.

`execute_command` resolves a command name dynamically on
`api.mesh_core.commands`, resolves contact arguments, and accepts `send_login`
and `send_cmd`. This is an advanced generic escape hatch rather than a stable
remote-command lifecycle contract.

## Actual transport paths

### Live environment

The configured transport for the actual HA entry is **unknown** because the
config entry and running coordinator were inaccessible.

### Audited 2.9.0 paths

The source baseline supports HA-to-local-companion transport over:

- USB serial;
- Bluetooth Low Energy; or
- TCP, normally port 5000.

The command path in that source is:

```text
HA service
  -> MeshCore integration service handler
  -> selected config-entry coordinator/API
  -> meshcore-py CommandHandler
  -> local companion transport
  -> mesh packet to selected remote contact
```

Optional MQTT upload is not the radio command path. No integration-specific
Home Assistant WebSocket command API is registered; ordinary clients may call
HA services using Home Assistant's generic WebSocket/API mechanisms.

## Confirmed local command capabilities

No local command was executed. The following are source-confirmed, not
live-confirmed:

| Operation | Baseline behavior | Evidence |
| --- | --- | --- |
| `get_time` | Reads the local companion clock through `commands.get_time()` | meshcore-py `commands/device.py`; 2.9.0 `services.py` allow-list |
| `set_time <epoch>` | Sets the local companion clock | meshcore-py `commands/device.py`; 2.9.0 `meshcore_api.py` reconnect/startup time sync |
| `reboot` | Reboots the local companion | meshcore-py `commands/device.py`; 2.9.0 `services.py` allow-list |

These operations do **not** target a remote repeater. MeshCore HA 2.9.0 also
calls local `set_time` after connect/reconnect. That is not remote `clock sync`.

## Confirmed remote command capabilities

No remote command was sent. The following are source-confirmed:

- `commands.send_login_sync(contact, password)` sends login and waits for
  `LOGIN_SUCCESS`;
- `commands.send_cmd(contact, command, timestamp=None)` sends remote CLI text;
- the generic 2.9.0 `execute_command` parser exposes `send_login` and
  `send_cmd` using a resolved contact;
- the SDK's receive path can emit `CONTACT_MSG_RECV`;
- the official repeater CLI vocabulary previously audited includes `clock`,
  `clock sync`, `time <epoch>`, `reboot`, and `clkreboot`.

The commands' presence in firmware documentation does not prove a particular
live repeater firmware supports them. No live firmware versions were available.

## Confirmed and missing response channels

### Confirmed in source

- `send_login_sync` waits for `LOGIN_SUCCESS`, under the SDK mesh-request lock.
- `send_cmd` waits only for local `MSG_SENT` or `ERROR`.
- incoming direct messages can surface as SDK `CONTACT_MSG_RECV` events.
- MeshCore HA 2.9.0 can normalize the immediate SDK result as an optional HA
  service response.
- with `record_to_console: true`, the same normalized immediate result can be
  recorded in the optional CLI console and fired as
  `meshcore_cli_response`.
- two config-flow checks demonstrate an internal pattern: subscribe/wait for
  `CONTACT_MSG_RECV`, send `ver`, then inspect the message.

### Missing from the supported HA contract

- no typed service returns the remote repeater's response text;
- no request ID is carried through remote CLI request and reply;
- no supported completion marker or multi-line response framing exists;
- `meshcore_cli_response` reports the service command result, which for
  `send_cmd` is send acceptance, not a correlated remote CLI reply;
- no supported service exposes cancellation;
- no supported per-target queue/lock/cooldown contract applies to generic
  `execute_command`;
- no supported remote reconnect/reboot-completion signal exists;
- no evidence shows a remote response in entity state or a stable event schema;
- logs and optional console transcript are diagnostic text, not an automation
  contract.

Matching the next direct message only by sender and time would be vulnerable to
unsolicited messages, overlapping consumers, polling traffic, delayed replies,
and multi-line output. NOC must not use that heuristic for operational actions.

## Compatibility with MeshCore HA 2.9.0

| Area | Live result | 2.9.0 source baseline | Difference affecting Phase 2 |
| --- | --- | --- | --- |
| Integration/version | Unknown | 2.9.0 | Cannot establish compatibility |
| Service registry | Unknown | `execute_command` exists | Cannot assume installed registration |
| `get_time`, `set_time`, `reboot` | Unknown | Local companion methods | Cannot treat as live or remote |
| Remote login | Unknown | `send_login_sync` in SDK; generic service exposes `send_login`, not typed login-sync lifecycle | Authentication behavior unverified |
| Remote `send_cmd` | Unknown | Dispatch supported | Send support does not equal response support |
| `clock` family | Firmware unknown | CLI text can be sent if firmware supports it | Exact live command/output unknown |
| Response | Unknown | Immediate send result; raw receive event exists internally | No stable correlated HA response |
| Timeout | Unknown | SDK waits have timeouts; `send_cmd` has no remote-response wait | Required remote timeout contract absent |
| Reconnect | Unknown | local companion reconnect and local time reset | No remote reboot/reconnect proof |

There are no verified installed differences because there is no installed
snapshot to compare. “Unknown” is deliberately not converted to “same.”

## Recommended proof-of-concept method

Run the existing-service live procedure in a disposable or explicitly selected
live HA environment against one managed repeater:

1. confirm installed versions, config entry, transport, contact mapping, and
   firmware;
2. enable an experimental NOC option that is false by default;
3. select exactly one managed repeater by stable HA `device_id`;
4. call the existing public `meshcore.execute_command` service with only the
   remote `clock` CLI text;
5. keep transport and addressing inside MeshCore while observing only public
   service results, events, entities, and registry data;
6. record the distinctions between service acceptance, send confirmation,
   passive response observation, and operational verification;
7. verify successful, timeout, disconnect, unsolicited-message, concurrent,
   cooldown, and restart cases;
8. keep sync, reboot, retries, automatic recovery, and UI controls absent.

Until that contract exists, a source-only mock would test an invented interface
and a live `send_cmd` would produce an ambiguous result. Neither is an acceptable
proof of concept.

## Historical typed-interface proposal (not required or pursued)

The following model records the interface that would have removed ambiguity.
It is retained as design context only. MeshCore NOC will not modify, fork,
patch, or depend on changes to the MeshCore Home Assistant integration.

Add a typed HA service, for example `meshcore.execute_remote_command`, with
`SupportsResponse.ONLY`.

Request:

```yaml
device_id: "<Home Assistant MeshCore repeater device ID>"
command: "clock"
request_id: "<caller UUID>"
timeout: 30
```

For the initial release, `command` must be an enum containing only `clock`.
Free-form CLI text is not needed for the NOC proof of concept.

Response:

```yaml
request_id: "<caller UUID>"
device_id: "<resolved Home Assistant device ID>"
command: "clock"
state: "completed"  # completed | timed_out | cancelled | error
sent_at: "2026-07-28T12:00:00Z"
completed_at: "2026-07-28T12:00:03Z"
send_result: "accepted"
response_text: "<bounded repeater reply or null>"
completion: true
timeout: false
error:
  code: null
  message: null
```

Required semantics:

- resolve HA `device_id` to one contact inside MeshCore integration;
- reject non-repeater, ambiguous, unavailable, or cross-entry targets;
- retain the remote password upstream and perform `send_login_sync` as needed;
- serialize requests per target and apply integration-wide radio limits;
- subscribe before sending and correlate by protocol request ID where possible;
- return bounded response text plus explicit completion;
- time out the whole login/send/receive lifecycle;
- support cancellation on service task cancellation, entry unload, and
  disconnect;
- invalidate in-flight sessions on local reconnect;
- report remote reboot as unknown until independent target evidence exists;
- never convert `MSG_SENT` into remote command completion.

If current firmware cannot echo a request ID or provide an end marker, extend
the protocol/firmware to carry them. A temporary single-flight sender match may
be acceptable for a human diagnostic tool only if explicitly labeled
uncorrelated; it is not sufficient for NOC automation.

## Risks and limitations

- Actual HA, integration, SDK, companion firmware, and repeater firmware
  versions remain unknown.
- No real service registry, schema, config entry, logs, events, or entity states
  were available.
- No hardware command was sent, so command spelling and output were not tested
  on the target fleet.
- The local host SDK may differ from HA's isolated Python environment.
- `MSG_SENT` confirms local/mesh submission, not remote execution.
- Remote CLI output may be delayed, unsolicited, split, or absent.
- Login success is not command success.
- Local companion reconnect is not remote repeater reconnect.
- Passwords and raw command strings may be sensitive and must be redacted.

## Evidence required to unblock runtime code

Provide read-only access to the running Home Assistant API/config environment or
an exported diagnostic bundle containing:

- HA version;
- MeshCore integration manifest and source revision;
- actual service descriptions/response modes;
- HA config-entry transport type with secrets redacted;
- meshcore-py distribution version;
- companion and selected repeater firmware versions;
- relevant service-response and event schemas; and
- a controlled capture of login, `clock`, timeout, disconnect, and reply
  behavior for one test repeater.

Runtime implementation remains blocked until live evidence confirms that the
installed public service/event/entity contract can safely support targeting,
authentication, lifecycle classification, and operational verification. The
exact procedure is in `V4_1_EXISTING_SERVICE_LIVE_TEST.md`.
