"use strict";

global.HTMLElement = class {};
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const frontendLogs = [];
const originalConsoleInfo = console.info;
console.info = (message) => frontendLogs.push(message);
const dashboard = require(path.resolve(
  __dirname,
  "../../custom_components/meshcore_noc/frontend/meshcore-noc-dashboard.js",
));
console.info = originalConsoleInfo;
assert.deepEqual(frontendLogs, ["MeshCore NOC frontend loaded"]);

const hass = {
  devices: {
    controller: {
      id: "controller",
      identifiers: [["meshcore_noc", "noc"]],
      config_entries: ["entry"],
    },
    managed: {
      id: "managed",
      name: "<img src=x onerror=alert(1)>",
      identifiers: [["meshcore_noc", "node/one"]],
      config_entries: ["entry"],
    },
    upstream: {
      id: "upstream",
      identifiers: [["meshcore", "unselected"]],
      config_entries: ["meshcore"],
    },
  },
  entities: {
    voltage: {
      entity_id: "sensor.managed_voltage",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_calibrated_voltage",
    },
    battery: {
      entity_id: "sensor.managed_battery",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_calibrated_battery_percentage",
    },
    health: {
      entity_id: "sensor.managed_health",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_health",
    },
    fresh: {
      entity_id: "binary_sensor.managed_fresh",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_fresh",
    },
    clockStatus: {
      entity_id: "sensor.managed_clock_status",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_clock_status",
    },
    clockOffset: {
      entity_id: "sensor.managed_clock_offset",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_clock_offset",
    },
    checkClock: {
      entity_id: "button.managed_check_clock",
      device_id: "managed",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "managed_repeater_node/one_check_clock",
    },
    fleetState: {
      entity_id: "sensor.clock_check_state",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_clock_check_state",
    },
    fleetProgress: {
      entity_id: "sensor.clock_check_progress",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_clock_check_progress",
    },
    fleetHealth: {
      entity_id: "sensor.fleet_clock_health",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_fleet_clock_health",
    },
    fleetRunning: {
      entity_id: "binary_sensor.clock_check_running",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_clock_check_running",
    },
    lastFleetCheck: {
      entity_id: "sensor.last_fleet_clock_check",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_last_fleet_clock_check",
    },
    checkAll: {
      entity_id: "button.check_all_clocks",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_check_all_clocks",
    },
    cancelClock: {
      entity_id: "button.cancel_clock_check",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_cancel_clock_check",
    },
    fleetSyncState: {
      entity_id: "sensor.fleet_clock_sync_state",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_fleet_clock_sync_state",
    },
    lastFleetSync: {
      entity_id: "sensor.last_fleet_clock_sync",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_last_fleet_clock_sync",
    },
    syncAll: {
      entity_id: "button.sync_all_repeater_clocks",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "noc_sync_all_repeater_clocks",
    },
    update: {
      entity_id: "update.meshcore_noc_update",
      device_id: "controller",
      platform: "meshcore_noc",
      config_entry_id: "entry",
      unique_id: "update",
    },
    helper: {
      entity_id: "input_number.old_helper",
      device_id: "managed",
      platform: "input_number",
      unique_id: "old_helper_calibrated_voltage",
    },
  },
  states: {
    "sensor.managed_battery": { state: "72", attributes: {} },
    "sensor.managed_health": { state: "healthy", attributes: {} },
    "binary_sensor.managed_fresh": { state: "on", attributes: {} },
    "sensor.managed_clock_status": {
      state: "Critical",
      attributes: {
        last_successful_clock_check: "2026-07-28T07:13:10+00:00",
        last_clock_attempt: "2026-07-28T08:13:10+00:00",
        last_clock_attempt_outcome: "timeout",
        clock_offset_seconds: -352,
      },
    },
    "sensor.managed_clock_offset": { state: "-352", attributes: {} },
    "sensor.clock_check_state": {
      state: "Running",
      attributes: {
        current_run: {
          current_friendly_name: "Laguna2",
          current_stable_id: "node/one",
          current_index: 4,
          total_repeaters: 8,
          completed_count: 2,
          success_count: 1,
          timeout_count: 1,
          failure_count: 0,
          remaining_count: 6,
          next_check_at: "2026-07-28T08:14:10+00:00",
          outcomes: [],
        },
        queue: ["node/one"],
        automatic_enabled: false,
      },
    },
    "sensor.fleet_clock_health": {
      state: "Critical",
      attributes: {
        in_sync: 2,
        minor_drift: 1,
        drift: 1,
        critical: 1,
        unknown: 3,
        critical_repeaters: ["<img src=x onerror=alert(1)>"],
      },
    },
    "binary_sensor.clock_check_running": { state: "on", attributes: {} },
    "sensor.last_fleet_clock_check": {
      state: "2026-07-28T08:13:10+00:00",
      attributes: {},
    },
    "sensor.fleet_clock_sync_state": {
      state: "idle",
      attributes: {
        fleet_sync_running: false,
        fleet_sync_completed_count: 3,
        fleet_sync_total_count: 3,
        last_fleet_sync_result: "completed",
        last_fleet_sync_successful: 2,
        last_fleet_sync_already_ahead: 1,
        last_fleet_sync_failed: 0,
        automatic_sync_enabled: false,
        automatic_sync_interval: 24,
      },
    },
    "sensor.last_fleet_clock_sync": {
      state: "2026-07-28T09:13:10+00:00",
      attributes: {},
    },
    "update.meshcore_noc_update": {
      state: "off",
      attributes: { installed_version: "1.0.0" },
    },
  },
};

const repeaters = dashboard.discoverRepeaters(hass);
assert.equal(repeaters.length, 1);
assert.equal(repeaters[0].stableId, "node/one");
assert.equal(repeaters[0].name, "<img src=x onerror=alert(1)>");
assert.equal(repeaters[0].entities.voltage, "sensor.managed_voltage");
assert.equal(repeaters[0].entities.checkClock, "button.managed_check_clock");
assert.equal(
  Object.values(repeaters[0].entities).includes("input_number.old_helper"),
  false,
);
const fleetClock = dashboard.discoverFleetClock(hass);
assert.equal(fleetClock.checkAll, "button.check_all_clocks");
assert.equal(fleetClock.cancel, "button.cancel_clock_check");
assert.equal(fleetClock.running, "binary_sensor.clock_check_running");
assert.equal(fleetClock.syncAll, "button.sync_all_repeater_clocks");
assert.equal(fleetClock.syncState, "sensor.fleet_clock_sync_state");
const runningFleet = dashboard.fleetClockMetrics(hass, fleetClock);
assert.equal(runningFleet.active, true);
assert.deepEqual(dashboard.fleetControlState(runningFleet), {
  checkAllDisabled: true,
  syncAllDisabled: true,
  cancelDisabled: false,
});
assert.equal(runningFleet.currentRepeater, "Laguna2");
assert.equal(runningFleet.currentIndex, 4);
assert.equal(runningFleet.total, 8);
assert.equal(runningFleet.health.critical, 1);
const idleFleetHass = structuredClone(hass);
idleFleetHass.states["sensor.clock_check_state"].state = "Idle";
assert.equal(
  dashboard.fleetClockMetrics(idleFleetHass, fleetClock).active,
  false,
);
assert.deepEqual(
  dashboard.fleetControlState(
    dashboard.fleetClockMetrics(idleFleetHass, fleetClock),
  ),
  { checkAllDisabled: false, syncAllDisabled: false, cancelDisabled: true },
);
const completedFleetHass = structuredClone(hass);
completedFleetHass.states["sensor.clock_check_state"] = {
  state: "Completed with errors",
  attributes: {
    current_run: {
      state: "completed_with_errors",
      total_repeaters: 8,
      completed_count: 8,
      success_count: 6,
      timeout_count: 1,
      failure_count: 1,
      remaining_count: 0,
      completed_at: "2026-07-28T08:20:10+00:00",
      total_duration_seconds: 420,
      outcomes: [
        {
          friendly_name: "Laguna2",
          state: "timed_out",
          error: "clock response timed out",
        },
        {
          friendly_name: "Vredenburg",
          state: "failed",
          error: "service call failed",
        },
      ],
    },
  },
};
const completedFleet = dashboard.fleetClockMetrics(
  completedFleetHass,
  fleetClock,
);
assert.equal(completedFleet.completed, 8);
assert.equal(completedFleet.success, 6);
assert.equal(completedFleet.timeout, 1);
assert.equal(completedFleet.failure, 1);
assert.deepEqual(
  completedFleet.failedRepeaters.map(({ name }) => name),
  ["Laguna2", "Vredenburg"],
);
assert.deepEqual(dashboard.clockSummaryTile(runningFleet.health), {
  value: "1 Critical",
  severity: "critical",
  context: "In Sync 2 · Minor 1 · Drift 1 · Critical 1 · Unknown 3",
});
assert.equal(
  dashboard.clockSummaryTile({
    inSync: 8,
    minorDrift: 0,
    drift: 0,
    critical: 0,
    unknown: 0,
  }).value,
  "8 In Sync",
);
assert.equal(
  dashboard.signedClockOffset(hass, "sensor.managed_clock_offset"),
  "−5m 52s",
);
assert.equal(dashboard.readableClockOffset(59), "+59 s");
assert.equal(dashboard.readableClockOffset(-3661), "−1h 1m");
const syncFleet = dashboard.fleetSyncMetrics(hass, fleetClock);
assert.equal(syncFleet.successful, 2);
assert.equal(syncFleet.alreadyAhead, 1);
assert.equal(syncFleet.interval, 24);
assert.equal(
  dashboard.repeaterClockBusy(hass, repeaters[0], runningFleet),
  true,
);
assert.equal(
  dashboard.actionRequestMessage("repeater", "Laguna2"),
  "Clock check requested for Laguna2",
);
assert.equal(
  dashboard.actionRequestMessage("fleet"),
  "Fleet clock check started",
);
assert.equal(
  dashboard.actionRequestMessage("fleet-sync"),
  "Fleet clock synchronisation started",
);
assert.equal(dashboard.actionRequestMessage("cancel"), "Cancel requested");
assert.equal(
  dashboard.clockCompletionMessage("timeout", "Laguna2"),
  "Check timed out for Laguna2",
);
assert.equal(
  dashboard.clockCompletionMessage("failed", "Vredenburg"),
  "Clock check failed for Vredenburg",
);
assert.equal(
  dashboard.clockStatusPresentation("Critical").className,
  "critical",
);
assert.equal(
  dashboard.clockStatusPresentation("Unknown").className,
  "unknown",
);
assert.notEqual(
  dashboard.clockStatusPresentation("Critical").icon,
  dashboard.clockStatusPresentation("Unknown").icon,
);
const failedAfterSuccess = structuredClone(hass);
failedAfterSuccess.states["sensor.managed_clock_status"].attributes.last_clock_attempt_outcome =
  "failed";
assert.equal(
  failedAfterSuccess.states["sensor.managed_clock_status"].state,
  "Critical",
);
const clockDashboardSource = fs.readFileSync(
  path.resolve(
    __dirname,
    "../../custom_components/meshcore_noc/frontend/meshcore-noc-dashboard.js",
  ),
  "utf8",
);
assert.equal(clockDashboardSource.includes("send_cmd"), false);
assert.equal(clockDashboardSource.includes("meshcore.execute_command"), false);
assert(clockDashboardSource.includes("Check All Clocks"));
assert(clockDashboardSource.includes("Synchronise All Clocks"));
assert(clockDashboardSource.includes("Synchronising…"));
assert(clockDashboardSource.includes("Clock Management"));
assert(
  clockDashboardSource.includes(
    "Repeaters are synchronised to the connected MeshCore companion clock",
  ),
);
assert(clockDashboardSource.includes("clock-result-row"));
assert(clockDashboardSource.includes("Cancel Check"));
assert(clockDashboardSource.includes("action-feedback"));
assert(clockDashboardSource.includes("Action failed:"));
assert(clockDashboardSource.includes("Working…"));
assert(clockDashboardSource.includes("Clock details"));
assert(clockDashboardSource.includes("grid.append(this._repeaterCard"));
const longNamed = structuredClone(hass);
longNamed.devices.managed.name =
  "Myburgh Park Solar Repeater With A Deliberately Long Operations Display Name";
assert.equal(
  dashboard.discoverRepeaters(longNamed)[0].name,
  longNamed.devices.managed.name,
);

const config = dashboard.generateDashboard(hass);
assert.equal(config.views.length, 2);
assert.equal(config.views[0].panel, true);
assert.equal(config.views[0].cards[0].type, "vertical-stack");
assert.equal(
  config.views[0].cards[0].cards[0].type,
  "custom:meshcore-noc-overview-card",
);
assert.equal(config.views[0].cards[0].cards[1].type, "horizontal-stack");
assert.equal(config.views[0].cards[0].cards[1].cards.length, 2);
assert.equal(config.views[0].cards[0].cards[1].cards[0].hours_to_show, 24);
assert.equal(config.views[0].cards[0].cards[1].cards[1].hours_to_show, 24);
assert.deepEqual(
  config.views[0].cards[0].cards[1].cards[0].grid_options,
  { columns: 12, rows: 4 },
);
assert.deepEqual(
  config.views[0].cards[0].cards[1].cards[1].grid_options,
  { columns: 12, rows: 4 },
);
assert.equal(config.views[1].title, "Trends");
assert.equal(config.views[1].cards[0].hours_to_show, 168);
assert.equal(config.views[1].cards[1].title, "Current battery comparison");
assert.equal(
  dashboard.generateDashboard({ devices: {}, entities: {}, states: {} }).views
    .length,
  1,
);
const metrics = dashboard.networkMetrics(hass, repeaters);
assert.equal(metrics.managed, 1);
assert.equal(metrics.online, 1);
assert.equal(metrics.offline, 0);
assert.equal(metrics.fresh, 1);
assert.equal(metrics.averageBattery, 72);
assert.equal(metrics.lowestBattery, 72);
assert.equal(metrics.lowestBatteryRepeater.name, hass.devices.managed.name);
assert.equal(metrics.health, 94);
assert.equal(dashboard.overallState(94), "healthy");
assert.equal(dashboard.overallState(80), "warning");
assert.equal(dashboard.overallState(60), "degraded");
assert.equal(dashboard.overallState(20), "critical");
assert.equal(dashboard.overallState(null), "unknown");
assert.equal(dashboard.clampBattery(-12), 0);
assert.equal(dashboard.clampBattery(112), 100);
assert.equal(dashboard.clampBattery(Number.NaN), null);
assert.equal(
  dashboard.installedVersionFromState(hass, Object.values(hass.entities)),
  "1.0.0",
);
const unknownMetrics = dashboard.networkMetrics(
  { ...hass, states: {} },
  repeaters,
);
assert.equal(unknownMetrics.averageBattery, null);
assert.equal(unknownMetrics.lowestBattery, null);
assert.equal(unknownMetrics.health, null);
assert.equal(unknownMetrics.online, 0);
assert.equal(unknownMetrics.lowestBatteryRepeater, null);
assert.equal(unknownMetrics.oldestUpdateRepeater, null);
const manyStates = {};
const manyRepeaters = Array.from({ length: 12 }, (_, index) => {
  const battery = `sensor.repeater_${index}_battery`;
  const freshness = `binary_sensor.repeater_${index}_fresh`;
  manyStates[battery] = { state: "80", attributes: {} };
  manyStates[freshness] = {
    state: "on",
    attributes: { freshness_status: "fresh", age_seconds: index * 10 },
  };
  return {
    stableId: `node-${index}`,
    name: `Node ${index}`,
    entities: { battery, freshness },
  };
});
assert.equal(
  dashboard.networkMetrics({ states: manyStates }, manyRepeaters).managed,
  12,
);
const fleetMetrics = dashboard.networkMetrics(
  {
    states: {
      "sensor.alpha_battery": { state: "13", attributes: {} },
      "binary_sensor.alpha_fresh": {
        state: "on",
        attributes: { freshness_status: "fresh", age_seconds: 7320 },
      },
      "sensor.beta_battery": { state: "82", attributes: {} },
      "binary_sensor.beta_fresh": {
        state: "on",
        attributes: { freshness_status: "fresh", age_seconds: 60 },
      },
    },
  },
  [
    {
      stableId: "alpha",
      name: "Myburgh Park",
      entities: {
        battery: "sensor.alpha_battery",
        freshness: "binary_sensor.alpha_fresh",
      },
    },
    {
      stableId: "beta",
      name: "Laguna2",
      entities: {
        battery: "sensor.beta_battery",
        freshness: "binary_sensor.beta_fresh",
      },
    },
  ],
);
assert.equal(fleetMetrics.lowestBattery, 13);
assert.equal(fleetMetrics.lowestBatteryRepeater.name, "Myburgh Park");
assert.equal(fleetMetrics.oldestUpdate, 7320);
assert.equal(fleetMetrics.oldestUpdateRepeater.name, "Myburgh Park");
assert.equal(fleetMetrics.firstAlert.repeater.name, "Myburgh Park");
assert.equal(fleetMetrics.firstAlert.alertReason, "battery 13%");

assert.deepEqual(dashboard.responsiveLayout(1650, 1080, 0), {
  columns: 1,
  density: "wide",
});
assert.equal(dashboard.responsiveLayout(1650, 1080, 1).columns, 1);
assert.equal(dashboard.responsiveLayout(1650, 1080, 8).columns, 4);
assert.equal(dashboard.responsiveLayout(1650, 1080, 12).columns, 4);
assert.equal(dashboard.responsiveLayout(1650, 1080, 20).columns, 5);
assert.equal(dashboard.responsiveLayout(1450, 900, 20).columns, 5);
assert.equal(dashboard.responsiveLayout(1150, 900, 20).columns, 4);
assert.equal(dashboard.responsiveLayout(950, 768, 20).columns, 3);
assert.equal(dashboard.responsiveLayout(650, 768, 20).columns, 1);
assert.equal(
  dashboard.responsiveLayout(1150, 768, 8).density,
  "compact",
);
assert.equal(
  dashboard.responsiveLayout(950, 700, 8).density,
  "constrained",
);
const frontendSource = fs.readFileSync(
  path.resolve(
    __dirname,
    "../../custom_components/meshcore_noc/frontend/meshcore-noc-dashboard.js",
  ),
  "utf8",
);
assert(!frontendSource.includes("const VERSION ="));
assert(frontendSource.includes('type: "manifest/get"'));
assert(!frontendSource.includes("scrollTop = 0"));
assert(!frontendSource.includes("scrollTo(0"));
assert(!frontendSource.includes("scrollIntoView"));
assert(!frontendSource.includes(".focus("));
assert(!frontendSource.includes("MESHCORE_NOC_SCROLL_DEBUG"));
assert(!frontendSource.includes("targetWindow.onerror"));
assert(!frontendSource.includes("targetWindow.onunhandledrejection"));
assert(!frontendSource.includes("_debugLog"));
assert(frontendSource.includes("shell.replaceChildren()"));
assert(
  frontendSource.includes('refreshOverviewCard(this, "connected")'),
);
assert(frontendSource.includes("if (!this.isConnected || !shell"));

const originalGetComputedStyle = global.getComputedStyle;
global.getComputedStyle = (element) => {
  if (element.nodeType !== 1)
    throw new TypeError("getComputedStyle requires an Element");
  return { overflowY: element.overflowY || "visible" };
};
const homeAssistantScrollContainer = {
  clientHeight: 700,
  nodeType: 1,
  overflowY: "auto",
  parentElement: null,
  scrollHeight: 1600,
  scrollTop: 640,
};
const shadowHost = {
  clientHeight: 700,
  nodeType: 1,
  parentElement: homeAssistantScrollContainer,
  scrollHeight: 700,
  scrollTop: 0,
};
const shadowRoot = {
  getRootNode() {
    return this;
  },
  host: shadowHost,
  nodeType: 11,
  parentElement: null,
  parentNode: null,
};
const dashboardCard = {
  parentElement: null,
  parentNode: shadowRoot,
};
assert.equal(
  dashboard.scrollContainerFor(dashboardCard),
  homeAssistantScrollContainer,
);
const stateUpdateSnapshot = dashboard.scrollSnapshotForRender(
  dashboardCard,
  true,
);
homeAssistantScrollContainer.scrollTop = 0;
dashboard.restoreScrollPosition(stateUpdateSnapshot);
assert.equal(homeAssistantScrollContainer.scrollTop, 640);

homeAssistantScrollContainer.scrollTop = 275;
const initialRenderSnapshot = dashboard.scrollSnapshotForRender(
  dashboardCard,
  false,
);
assert.equal(initialRenderSnapshot, null);
dashboard.restoreScrollPosition(initialRenderSnapshot);
assert.equal(homeAssistantScrollContainer.scrollTop, 275);
global.getComputedStyle = originalGetComputedStyle;

class FakeNode {
  constructor(tagName, attributes = {}, children = []) {
    this.nodeType = tagName ? 1 : 3;
    this.tagName = tagName?.toUpperCase();
    this.nodeValue = tagName ? null : attributes.text;
    this.attributes = new Map(Object.entries(tagName ? attributes : {}));
    this.childNodes = [];
    this.parentNode = null;
    for (const child of children) this.append(child);
  }

  getAttributeNames() {
    return Array.from(this.attributes.keys());
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  append(child) {
    child.parentNode = this;
    this.childNodes.push(child);
  }

  cloneNode(deep) {
    return new FakeNode(
      this.tagName,
      Object.fromEntries(this.attributes),
      deep ? this.childNodes.map((child) => child.cloneNode(true)) : [],
    );
  }

  replaceWith(replacement) {
    const index = this.parentNode.childNodes.indexOf(this);
    replacement.parentNode = this.parentNode;
    this.parentNode.childNodes[index] = replacement;
    this.parentNode = null;
  }

  remove() {
    const index = this.parentNode.childNodes.indexOf(this);
    this.parentNode.childNodes.splice(index, 1);
    this.parentNode = null;
  }

  get isConnected() {
    return Boolean(this._connected || this.parentNode?.isConnected);
  }
}

const textNode = (text) => new FakeNode(null, { text });
const stableCard = new FakeNode(
  "article",
  { class: "repeater healthy" },
  [new FakeNode("span", {}, [textNode("72%")])],
);
const stableShell = new FakeNode("section", { class: "shell" }, [stableCard]);
stableShell._connected = true;
const updatedDraft = new FakeNode(
  "section",
  {},
  [
    new FakeNode(
      "article",
      { class: "repeater warning" },
      [new FakeNode("span", {}, [textNode("28%")])],
    ),
  ],
);
dashboard.reconcileChildren(stableShell, updatedDraft);
assert.equal(stableShell.childNodes[0], stableCard);
assert.equal(stableCard.parentNode, stableShell);
assert.equal(stableCard.isConnected, true);
assert.equal(stableCard.getAttribute("class"), "repeater warning");
assert.equal(stableCard.childNodes[0].childNodes[0].nodeValue, "28%");
const openDetails = new FakeNode("details", {}, [textNode("Clock details")]);
openDetails.open = true;
const detailsShell = new FakeNode("section", {}, [openDetails]);
dashboard.reconcileChildren(
  detailsShell,
  new FakeNode("section", {}, [
    new FakeNode("details", {}, [textNode("Updated clock details")]),
  ]),
);
assert.equal(openDetails.open, true);
assert.equal(openDetails.childNodes[0].nodeValue, "Updated clock details");

const repeatersForStructure = [{ stableId: "one" }, { stableId: "two" }];
const originalStructure = dashboard.overviewStructureKey(
  { section: "operations" },
  repeatersForStructure,
);
assert.equal(
  dashboard.overviewStructureKey(
    { section: "operations" },
    repeatersForStructure,
  ),
  originalStructure,
);
assert.notEqual(
  dashboard.overviewStructureKey(
    { section: "operations" },
    [...repeatersForStructure, { stableId: "three" }],
  ),
  originalStructure,
);
assert.notEqual(
  dashboard.overviewStructureKey(
    { section: "alerts" },
    repeatersForStructure,
  ),
  originalStructure,
);

const startupCalls = [];
const startupCard = {
  isConnected: false,
  _hass: { states: {} },
  _config: undefined,
  shadowRoot: null,
  _ensureRegistrySubscriptions: () => startupCalls.push("subscriptions"),
  _ensureResponsiveLayout: () => startupCalls.push("responsive"),
  _ensureVersion: () => startupCalls.push("version"),
  _render: (reason) => startupCalls.push(reason),
};
assert.equal(
  dashboard.refreshOverviewCard(startupCard, "hass-state-update"),
  false,
);
assert.deepEqual(startupCalls, []);

const startupShell = { childNodes: [] };
startupCard._config = {
  section: "operations",
  registry_devices: [],
  registry_entities: [],
};
startupCard.shadowRoot = {
  querySelector: (selector) => (selector === ".shell" ? startupShell : null),
};
assert.equal(
  dashboard.refreshOverviewCard(startupCard, "config-initialization"),
  false,
);
assert.deepEqual(startupCalls, []);
startupCard.isConnected = true;
assert.equal(
  dashboard.refreshOverviewCard(startupCard, "connected"),
  true,
);
assert.deepEqual(startupCalls, [
  "subscriptions",
  "responsive",
  "version",
  "connected",
]);
assert.equal(
  dashboard.canReconcileOverview(
    false,
    undefined,
    originalStructure,
    startupShell,
  ),
  false,
);
startupShell.childNodes.push(stableCard);
assert.equal(
  dashboard.canReconcileOverview(
    true,
    originalStructure,
    originalStructure,
    startupShell,
  ),
  true,
);
assert.equal(
  dashboard.canReconcileOverview(
    true,
    originalStructure,
    dashboard.overviewStructureKey(
      { section: "operations" },
      [...repeatersForStructure, { stableId: "three" }],
    ),
    startupShell,
  ),
  false,
);
startupCalls.length = 0;
assert.equal(
  dashboard.refreshOverviewCard(startupCard, "hass-state-update"),
  true,
);
assert.deepEqual(startupCalls, [
  "subscriptions",
  "responsive",
  "version",
  "hass-state-update",
]);

const definitions = new Map();
const target = {};
const registry = {
  get: (name) => definitions.get(name),
  define: (name, value) => definitions.set(name, value),
};
dashboard.registerStrategy(target, registry);
dashboard.registerStrategy(target, registry);
assert(definitions.has("ll-strategy-dashboard-meshcore-noc"));
assert.equal(target.customStrategies.length, 1);
assert.equal(target.customStrategies[0].strategyType, "dashboard");
assert.equal(target.customStrategies[0].type, "meshcore-noc");
assert.equal(target.customStrategies[0].name, "MeshCore NOC");
assert.equal(
  target.customStrategies[0].description,
  "Dynamic Network Operations Centre dashboard for managed MeshCore repeaters",
);
assert.equal(target.customStrategies[0].icon, "mdi:access-point-network");
assert(
  definitions.has(
    `ll-strategy-dashboard-${target.customStrategies[0].type}`,
  ),
  "picker metadata type must resolve to the registered custom element",
);

const strategyClass = definitions.get(
  "ll-strategy-dashboard-meshcore-noc",
);
strategyClass
  .generate(
    {},
    {
      ...hass,
      callWS: async ({ type }) =>
        type === "config/device_registry/list"
          ? Object.values(hass.devices)
          : Object.values(hass.entities),
    },
  )
  .then((generated) => assert.equal(generated.views.length, 2));

const changed = structuredClone(hass);
changed.devices.second = {
  id: "second",
  name: "Second repeater",
  identifiers: [["meshcore_noc", "node-two"]],
  config_entries: ["entry"],
};
changed.entities.secondHealth = {
  entity_id: "sensor.second_health",
  device_id: "second",
  platform: "meshcore_noc",
  config_entry_id: "entry",
  unique_id: "managed_repeater_node-two_health",
};
assert.equal(dashboard.discoverRepeaters(changed).length, 2);
delete changed.devices.managed;
assert.deepEqual(
  dashboard.discoverRepeaters(changed).map((item) => item.stableId),
  ["node-two"],
);
changed.states["sensor.second_health"] = {
  state: "unavailable",
  attributes: {},
};
assert.equal(
  dashboard.repeaterStatus(changed, dashboard.discoverRepeaters(changed)[0])
    .label,
  "unknown",
);

const repeatedDefinitions = new Map();
const repeatedWindow = {};
global.window = repeatedWindow;
global.customElements = {
  get: (name) => repeatedDefinitions.get(name),
  define: (name, value) => repeatedDefinitions.set(name, value),
};
const modulePath = path.resolve(
  __dirname,
  "../../custom_components/meshcore_noc/frontend/meshcore-noc-dashboard.js",
);
delete require.cache[modulePath];
require(modulePath);
delete require.cache[modulePath];
require(modulePath);
assert.equal(repeatedWindow.customStrategies.length, 1);
assert(repeatedDefinitions.has("ll-strategy-dashboard-meshcore-noc"));
