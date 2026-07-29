/* MeshCore NOC bundled dashboard strategy. No external dependencies. */
(() => {
  "use strict";
  const loadMarker = "__meshcoreNocFrontendLoaded";
  if (!globalThis[loadMarker]) {
    globalThis[loadMarker] = true;
    console.info("MeshCore NOC frontend loaded");
  }
  const DOMAIN = "meshcore_noc";
  const STRATEGY_PICKER_TYPE = "meshcore-noc";
  const STRATEGY = "custom:meshcore-noc";
  const HTMLElementBase = globalThis.HTMLElement || class {};
  const ROLES = {
    calibrated_voltage: "voltage",
    calibrated_battery_percentage: "battery",
    health: "health",
    fresh: "freshness",
    clock_offset: "clockOffset",
    clock_status: "clockStatus",
    check_clock: "checkClock",
  };
  const FLEET_ROLES = {
    noc_clock_check_progress: "progress",
    noc_clock_check_state: "state",
    noc_last_fleet_clock_check: "lastCheck",
    noc_fleet_clock_health: "health",
    noc_clock_check_running: "running",
    noc_check_all_clocks: "checkAll",
    noc_cancel_clock_check: "cancel",
    noc_fleet_clock_sync_state: "syncState",
    noc_last_fleet_clock_sync: "lastSync",
    noc_sync_all_repeater_clocks: "syncAll",
  };
  const values = (object) => Object.values(object || {});
  const composedParent = (element) =>
    element?.assignedSlot ||
    element?.parentElement ||
    element?.parentNode ||
    element?.getRootNode?.()?.host ||
    null;
  const scrollContainerFor = (element) => {
    for (
      let candidate = composedParent(element);
      candidate;
      candidate = composedParent(candidate)
    ) {
      if (candidate.nodeType !== 1) continue;
      const overflowY =
        globalThis.getComputedStyle?.(candidate)?.overflowY || "";
      if (
        candidate.scrollHeight > candidate.clientHeight &&
        (candidate.scrollTop > 0 ||
          ["auto", "scroll", "overlay"].includes(overflowY))
      )
        return candidate;
    }
    return globalThis.document?.scrollingElement || null;
  };
  const scrollSnapshotForRender = (element, hasRendered) => {
    if (!hasRendered) return null;
    const container = scrollContainerFor(element);
    return container ? { container, scrollTop: container.scrollTop } : null;
  };
  const restoreScrollPosition = (snapshot) => {
    if (snapshot) snapshot.container.scrollTop = snapshot.scrollTop;
  };
  const syncAttributes = (current, next) => {
    const nextNames = new Set(next.getAttributeNames());
    for (const name of current.getAttributeNames())
      if (!nextNames.has(name)) current.removeAttribute(name);
    for (const name of nextNames) {
      const value = next.getAttribute(name);
      if (current.getAttribute(name) !== value)
        current.setAttribute(name, value);
    }
  };
  const reconcileNode = (current, next) => {
    if (
      current.nodeType !== next.nodeType ||
      (current.nodeType === 1 && current.tagName !== next.tagName)
    ) {
      current.replaceWith(next.cloneNode(true));
      return;
    }
    if (current.nodeType === 3) {
      if (current.nodeValue !== next.nodeValue)
        current.nodeValue = next.nodeValue;
      return;
    }
    const detailsOpen =
      current.tagName === "DETAILS" && Boolean(current.open);
    syncAttributes(current, next);
    reconcileChildren(current, next);
    if (current.tagName === "DETAILS") current.open = detailsOpen;
  };
  const reconcileChildren = (current, next) => {
    const currentChildren = Array.from(current.childNodes);
    const nextChildren = Array.from(next.childNodes);
    for (let index = 0; index < nextChildren.length; index += 1) {
      if (currentChildren[index])
        reconcileNode(currentChildren[index], nextChildren[index]);
      else current.append(nextChildren[index].cloneNode(true));
    }
    for (
      let index = currentChildren.length - 1;
      index >= nextChildren.length;
      index -= 1
    )
      currentChildren[index].remove();
  };
  const overviewStructureKey = (config, repeaters) =>
    JSON.stringify([
      config?.section || "operations",
      ...repeaters.map((repeater) => repeater.stableId),
    ]);
  const canReconcileOverview = (
    hasRendered,
    previousStructureKey,
    structureKey,
    shell,
  ) =>
    Boolean(
      hasRendered &&
      previousStructureKey === structureKey &&
      shell?.childNodes?.length,
    );
  const refreshOverviewCard = (card, reason) => {
    if (
      !card.isConnected ||
      !card._hass ||
      !card._config ||
      !card.shadowRoot?.querySelector(".shell")
    )
      return false;
    card._ensureRegistrySubscriptions();
    card._ensureResponsiveLayout();
    card._ensureVersion();
    card._render(reason);
    return true;
  };
  const stableIdForDevice = (device) => {
    const identifiers =
      device?.identifiers instanceof Set
        ? Array.from(device.identifiers)
        : device?.identifiers || [];
    for (const identifier of identifiers) {
      if (
        Array.isArray(identifier) &&
        identifier[0] === DOMAIN &&
        identifier[1] !== "noc"
      )
        return String(identifier[1]);
    }
    return null;
  };
  const roleForEntity = (entity) => {
    if (entity?.platform !== DOMAIN || typeof entity.unique_id !== "string")
      return null;
    return (
      Object.entries(ROLES).find(([suffix]) =>
        entity.unique_id.endsWith(`_${suffix}`),
      )?.[1] || null
    );
  };
  const discoverRepeaters = (hass) => {
    const registryEntities = values(hass.entities);
    const nocEntryIds = new Set(
      registryEntities
        .filter((entity) => entity.platform === DOMAIN && entity.config_entry_id)
        .map((entity) => entity.config_entry_id),
    );
    return values(hass.devices)
      .map((device) => ({ device, stableId: stableIdForDevice(device) }))
      .filter(({ device, stableId }) => {
        if (!stableId) return false;
        const entryIds = device.config_entries || device.config_entry_ids || [];
        return (
          nocEntryIds.size === 0 ||
          Array.from(entryIds).some((entryId) => nocEntryIds.has(entryId))
        );
      })
      .map(({ device, stableId }) => {
        const entities = {};
        for (const entity of registryEntities) {
          if (entity.device_id !== device.id) continue;
          const role = roleForEntity(entity);
          if (role) entities[role] = entity.entity_id;
        }
        return {
          stableId,
          deviceId: device.id,
          name: device.name_by_user || device.name || stableId,
          entities,
        };
      })
      .filter((item) => Object.keys(item.entities).length)
      .sort((left, right) => left.name.localeCompare(right.name));
  };
  const discoverFleetClock = (hass) => {
    const entities = {};
    for (const entity of values(hass.entities)) {
      if (entity.platform !== DOMAIN) continue;
      const role = FLEET_ROLES[entity.unique_id];
      if (role) entities[role] = entity.entity_id;
    }
    return entities;
  };
  const safePath = (stableId) => {
    const slug = stableId
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 36);
    let hash = 2166136261;
    for (const character of stableId) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return `repeater-${slug || "managed"}-${(hash >>> 0).toString(36)}`;
  };
  const stateValue = (hass, entityId) => hass.states?.[entityId];
  const normalized = (state) =>
    state && !["unknown", "unavailable"].includes(state.state)
      ? state.state.toLowerCase()
      : "unknown";
  const clockStatusPresentation = (state) => {
    const normalizedState = String(state || "Unknown").toLowerCase();
    return (
      {
        "in sync": {
          label: "In Sync",
          className: "healthy",
          icon: "mdi:clock-check",
        },
        "minor drift": {
          label: "Minor Drift",
          className: "warning",
          icon: "mdi:clock-alert-outline",
        },
        drift: {
          label: "Drift",
          className: "degraded",
          icon: "mdi:clock-alert-outline",
        },
        critical: {
          label: "Critical",
          className: "critical",
          icon: "mdi:clock-alert",
        },
      }[normalizedState] || {
        label: "Unknown",
        className: "unknown",
        icon: "mdi:clock-question-outline",
      }
    );
  };
  const fleetClockMetrics = (hass, fleet) => {
    const state = stateValue(hass, fleet.state);
    const run = state?.attributes?.current_run || {};
    const health = stateValue(hass, fleet.health)?.attributes || {};
    const lifecycle = String(state?.state || "Idle").toLowerCase();
    const active = ["queued", "running", "waiting", "cancelling"].includes(
      lifecycle,
    );
    return {
      lifecycle,
      active,
      currentRepeater: run.current_friendly_name || "—",
      currentStableId: run.current_stable_id || null,
      currentIndex: run.current_index ?? 0,
      total: run.total_repeaters ?? 0,
      completed: run.completed_count ?? 0,
      success: run.success_count ?? 0,
      timeout: run.timeout_count ?? 0,
      failure: run.failure_count ?? 0,
      remaining: run.remaining_count ?? 0,
      nextScheduledRun: state?.attributes?.next_scheduled_run || null,
      nextCheckAt: run.next_check_at || null,
      completedAt: run.completed_at || null,
      totalDurationSeconds: run.total_duration_seconds ?? null,
      queuedStableIds: state?.attributes?.queue || [],
      failedRepeaters: (run.outcomes || [])
        .filter((outcome) =>
          ["failed", "timed_out"].includes(String(outcome.state)),
        )
        .map((outcome) => ({
          name: outcome.friendly_name || "Managed repeater",
          outcome: String(outcome.state).replace("_", " "),
          error: outcome.error || null,
        })),
      automaticEnabled:
        stateValue(hass, fleet.health)?.attributes?.automatic_enabled ??
        state?.attributes?.automatic_enabled ??
        false,
      health: {
        inSync: health.in_sync ?? 0,
        minorDrift: health.minor_drift ?? 0,
        drift: health.drift ?? 0,
        critical: health.critical ?? 0,
        unknown: health.unknown ?? 0,
        driftRepeaters: health.drift_repeaters || [],
        criticalRepeaters: health.critical_repeaters || [],
      },
    };
  };
  const clockSummaryTile = (health) => {
    const counts = health || {};
    const critical = counts.critical ?? 0;
    const drift = counts.drift ?? 0;
    const minor = counts.minorDrift ?? counts.minor_drift ?? 0;
    const inSync = counts.inSync ?? counts.in_sync ?? 0;
    const unknown = counts.unknown ?? 0;
    let value = "Unknown";
    let severity = "unknown";
    if (critical) {
      value = `${critical} Critical`;
      severity = "critical";
    } else if (drift) {
      value = `${drift} Drift`;
      severity = "degraded";
    } else if (minor) {
      value = `${minor} Minor`;
      severity = "warning";
    } else if (inSync) {
      value = `${inSync} In Sync`;
      severity = "healthy";
    }
    return {
      value,
      severity,
      context: `In Sync ${inSync} · Minor ${minor} · Drift ${drift} · Critical ${critical} · Unknown ${unknown}`,
    };
  };
  const signedClockOffset = (hass, entityId) => {
    const value = numericState(hass, entityId);
    return readableClockOffset(value);
  };
  const readableClockOffset = (value) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value)))
      return "—";
    const rounded = Math.round(Number(value));
    const sign = rounded > 0 ? "+" : rounded < 0 ? "−" : "";
    const absolute = Math.abs(rounded);
    if (absolute < 60) return `${sign}${absolute} s`;
    if (absolute < 3600)
      return `${sign}${Math.floor(absolute / 60)}m ${absolute % 60}s`;
    return `${sign}${Math.floor(absolute / 3600)}h ${Math.floor(
      (absolute % 3600) / 60,
    )}m`;
  };
  const fleetSyncMetrics = (hass, fleet) => {
    const state = stateValue(hass, fleet.syncState);
    const attributes = state?.attributes || {};
    return {
      lifecycle: String(state?.state || "idle").toLowerCase(),
      active: Boolean(attributes.fleet_sync_running),
      currentRepeater: attributes.fleet_sync_current_repeater || "—",
      completed: attributes.fleet_sync_completed_count ?? 0,
      total: attributes.fleet_sync_total_count ?? 0,
      result: attributes.last_fleet_sync_result || "—",
      successful: attributes.last_fleet_sync_successful ?? 0,
      alreadyAhead: attributes.last_fleet_sync_already_ahead ?? 0,
      failed: attributes.last_fleet_sync_failed ?? 0,
      automaticEnabled: attributes.automatic_sync_enabled ?? false,
      interval: attributes.automatic_sync_interval ?? 24,
      nextAutomaticSync: attributes.next_automatic_sync || null,
      perRepeater: attributes.last_summary?.per_repeater || [],
    };
  };
  const repeaterClockBusy = (hass, repeater, fleetMetrics, syncMetrics = {}) => {
    const requestState = String(
      stateValue(hass, repeater.entities.clockStatus)?.attributes
        ?.request_state || "",
    );
    const individuallyActive = [
      "queued",
      "calling_service",
      "sent",
    ].includes(requestState);
    const reservedByFleet =
      fleetMetrics.active &&
      (fleetMetrics.currentStableId === repeater.stableId ||
        fleetMetrics.queuedStableIds.includes(repeater.stableId));
    return individuallyActive || reservedByFleet || Boolean(syncMetrics.active);
  };
  const actionRequestMessage = (kind, targetName) =>
    kind === "fleet"
      ? "Fleet clock check started"
      : kind === "fleet-sync"
        ? "Fleet clock synchronisation started"
      : kind === "cancel"
        ? "Cancel requested"
        : `Clock check requested for ${targetName || "managed repeater"}`;
  const fleetControlState = (metrics, syncMetrics = {}) => ({
    checkAllDisabled: metrics.active || Boolean(syncMetrics.active),
    syncAllDisabled: metrics.active || Boolean(syncMetrics.active),
    cancelDisabled: !metrics.active,
  });
  const clockCompletionMessage = (outcome, targetName) => {
    const name = targetName || "managed repeater";
    if (outcome === "timeout") return `Check timed out for ${name}`;
    if (["failed", "malformed"].includes(outcome))
      return `Clock check failed for ${name}`;
    if (outcome === "success") return `Clock check completed for ${name}`;
    return null;
  };
  const repeaterStatus = (hass, repeater) => {
    const healthState = normalized(
      stateValue(hass, repeater.entities.health),
    );
    const freshnessState = stateValue(hass, repeater.entities.freshness);
    const freshnessAttribute =
      freshnessState?.attributes?.freshness_status?.toLowerCase();
    const freshness = ["fresh", "aging", "stale", "offline"].includes(
      freshnessAttribute,
    )
      ? freshnessAttribute
      : normalized(freshnessState) === "on"
        ? "fresh"
        : "unknown";
    const health =
      {
        excellent: "healthy",
        good: "healthy",
        fair: "aging",
        poor: "unhealthy",
      }[healthState] || healthState;
    const battery = Number(stateValue(hass, repeater.entities.battery)?.state);
    let label = freshness;
    if (health === "offline" || freshness === "offline") label = "offline";
    else if (health === "critical") label = "critical";
    else if (health === "unhealthy") label = "degraded";
    else if (freshness === "stale") label = "stale";
    else if (
      freshness === "aging" ||
      ["aging", "warning"].includes(health)
    )
      label = "warning";
    const alert =
      ["offline", "critical", "degraded", "stale"].includes(label) ||
      ["offline", "unhealthy", "critical"].includes(health) ||
      (Number.isFinite(battery) && battery < 15);
    const alertReason =
      Number.isFinite(battery) && battery < 15
        ? `battery ${Math.round(battery)}%`
        : label;
    return { health, freshness, battery, label, alert, alertReason };
  };
  const numericState = (hass, entityId) => {
    const state = stateValue(hass, entityId);
    if (!state || ["unknown", "unavailable", ""].includes(state.state))
      return null;
    const value = Number(state.state);
    return Number.isFinite(value) ? value : null;
  };
  const clampBattery = (value) =>
    Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : null;
  const repeaterAgeSeconds = (hass, repeater) => {
    const ages = entityRows(repeater)
      .map((entityId) =>
        Number(stateValue(hass, entityId)?.attributes?.age_seconds),
      )
      .filter((age) => Number.isFinite(age) && age >= 0);
    return ages.length ? Math.min(...ages) : null;
  };
  const formatAge = (seconds) => {
    if (!Number.isFinite(seconds)) return "—";
    if (seconds < 60) return `${Math.round(seconds)} sec ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} hr ago`;
    return `${Math.round(seconds / 86400)} d ago`;
  };
  const formatDateTime = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  };
  const responsiveLayout = (width, height, repeaterCount) => {
    const availableWidth = Number.isFinite(width) ? width : 0;
    const availableHeight = Number.isFinite(height) ? height : 0;
    const count = Math.max(0, repeaterCount);
    let columns;
    if (availableWidth < 700) columns = 1;
    else if (count <= 1) columns = 1;
    else if (count <= 4) columns = 2;
    else if (availableWidth < 1050) columns = 3;
    else if (count >= 17 && availableWidth >= 1450) columns = 5;
    else columns = 4;
    const density =
      availableHeight >= 900 && availableWidth >= 1450
        ? "wide"
        : availableHeight >= 740 && availableWidth >= 1050
          ? "compact"
          : "constrained";
    return { columns, density };
  };
  const networkMetrics = (hass, repeaters) => {
    const statuses = repeaters.map((repeater) => ({
      repeater,
      ...repeaterStatus(hass, repeater),
    }));
    const knownStatuses = statuses.filter(({ label }) => label !== "unknown");
    const knownFreshness = statuses.filter(({ freshness }) =>
      ["fresh", "aging", "stale", "offline"].includes(freshness),
    );
    const batteryReadings = statuses
      .map(({ repeater }) => ({
        repeater,
        value: clampBattery(
          numericState(hass, repeater.entities.battery),
        ),
      }))
      .filter(({ value }) => value !== null);
    const batteries = batteryReadings.map(({ value }) => value);
    const ageReadings = statuses
      .map(({ repeater }) => ({
        repeater,
        value: repeaterAgeSeconds(hass, repeater),
      }))
      .filter(({ value }) => Number.isFinite(value));
    const validTelemetry = ({ repeater }) =>
      numericState(hass, repeater.entities.voltage) !== null ||
      numericState(hass, repeater.entities.battery) !== null;
    const online = statuses.filter(
      (status) => status.label !== "offline" && validTelemetry(status),
    ).length;
    const offline = statuses.filter(({ label }) => label === "offline").length;
    const fresh = statuses.filter(({ freshness }) => freshness === "fresh").length;
    const alerts = statuses.filter(({ alert }) => alert).length;
    const averageBattery = batteries.length
      ? batteries.reduce((sum, value) => sum + value, 0) / batteries.length
      : null;
    const lowestBatteryReading = batteryReadings.reduce(
      (lowest, reading) =>
        lowest === null || reading.value < lowest.value ? reading : lowest,
      null,
    );
    const oldestUpdateReading = ageReadings.reduce(
      (oldest, reading) =>
        oldest === null || reading.value > oldest.value ? reading : oldest,
      null,
    );
    const firstAlert = statuses.find(({ alert }) => alert) || null;

    /*
     * Network health uses only components with valid observations:
     * availability 50% (known non-offline / known status), freshness 30%
     * (fresh / known freshness), and battery condition 20% (mean calibrated
     * battery / 100). Missing components are omitted and remaining weights are
     * normalized. Availability plus at least one telemetry component is
     * required; otherwise the result is unknown rather than an invented zero.
     */
    const availability = knownStatuses.length
      ? knownStatuses.filter(({ label }) => label !== "offline").length /
        knownStatuses.length
      : null;
    const freshness = knownFreshness.length
      ? knownFreshness.filter(({ freshness: value }) => value === "fresh").length /
        knownFreshness.length
      : null;
    const batteryCondition =
      averageBattery === null ? null : averageBattery / 100;
    const components = [
      [availability, 0.5],
      [freshness, 0.3],
      [batteryCondition, 0.2],
    ].filter(([value]) => value !== null);
    const health =
      availability !== null &&
      (freshness !== null || batteryCondition !== null)
        ? Math.round(
            (components.reduce(
              (total, [value, weight]) => total + value * weight,
              0,
            ) /
              components.reduce((total, [, weight]) => total + weight, 0)) *
              100,
          )
        : null;
    return {
      managed: repeaters.length,
      online,
      offline,
      alerts,
      firstAlert,
      averageBattery,
      lowestBattery: lowestBatteryReading?.value ?? null,
      lowestBatteryRepeater: lowestBatteryReading?.repeater ?? null,
      oldestUpdate: oldestUpdateReading?.value ?? null,
      oldestUpdateRepeater: oldestUpdateReading?.repeater ?? null,
      fresh,
      health,
      statuses,
    };
  };
  const overallState = (score) => {
    if (!Number.isFinite(score)) return "unknown";
    if (score >= 90) return "healthy";
    if (score >= 75) return "warning";
    if (score >= 50) return "degraded";
    return "critical";
  };
  const installedVersionFromState = (hass, registryEntities) => {
    const updateEntity = (registryEntities || []).find(
      (entity) =>
        entity.platform === DOMAIN && entity.entity_id?.startsWith("update."),
    );
    const version = stateValue(
      hass,
      updateEntity?.entity_id,
    )?.attributes?.installed_version;
    return typeof version === "string" && version ? version : null;
  };
  const entityRows = (repeater) =>
    Object.values(repeater.entities).filter(Boolean);
  const historyCard = (title, entities, hours) => ({
    type: "history-graph",
    title,
    hours_to_show: hours,
    entities: entities.filter(Boolean),
    grid_options: { columns: 12, rows: 4 },
  });
  const generateDashboard = (hass) => {
    const repeaters = discoverRepeaters(hass);
    const voltages = repeaters.map((item) => item.entities.voltage);
    const batteries = repeaters.map((item) => item.entities.battery);
    const registry = {
      registry_devices: values(hass.devices),
      registry_entities: values(hass.entities),
    };
    const mainCards = [
      {
        type: "custom:meshcore-noc-overview-card",
        section: "operations",
        ...registry,
      },
    ];
    const primaryGraphs = [];
    if (voltages.some(Boolean))
      primaryGraphs.push(
        historyCard("Calibrated voltage — 24 hours", voltages, 24),
      );
    if (batteries.some(Boolean))
      primaryGraphs.push(
        historyCard("Battery percentage — 24 hours", batteries, 24),
      );
    if (primaryGraphs.length)
      mainCards.push({ type: "horizontal-stack", cards: primaryGraphs });
    mainCards.push({
      type: "custom:meshcore-noc-overview-card",
      section: "alerts",
      ...registry,
    });
    const views = [
      {
        title: "Mission Control",
        path: "network",
        icon: "mdi:access-point-network",
        panel: true,
        cards: [{ type: "vertical-stack", cards: mainCards }],
      },
    ];
    if (batteries.some(Boolean))
      views.push({
        title: "Trends",
        path: "trends",
        icon: "mdi:chart-line",
        cards: [
          historyCard("Battery trend — 7 days", batteries, 168),
          {
            type: "entities",
            title: "Current battery comparison",
            entities: batteries.filter(Boolean),
          },
          {
            type: "markdown",
            content:
              "History graphs use Home Assistant Recorder. Current values remain available when history is disabled.",
          },
        ],
      });
    return {
      title: "MeshCore NOC",
      views,
    };
  };
  class MeshCoreNocDashboardStrategy {
    static getCreateSuggestions() {
      return {
        title: "MeshCore NOC",
        icon: "mdi:access-point-network",
      };
    }
    static async generate(_config, hass) {
      const [devices, entities] = await Promise.all([
        hass.callWS({ type: "config/device_registry/list" }),
        hass.callWS({ type: "config/entity_registry/list" }),
      ]);
      return generateDashboard({ ...hass, devices, entities });
    }
  }
  class MeshCoreNocOverviewCard extends HTMLElementBase {
    setConfig(config) {
      this._config = config || {};
      if (!this.shadowRoot) {
        this.attachShadow({ mode: "open" });
        this.shadowRoot.innerHTML = `<style>
:host{display:block;container-type:inline-size;--noc-background:#101418;--noc-panel:#1a2128;--noc-panel-alt:#202832;--noc-border:rgba(255,255,255,.10);--noc-text-primary:#f3f6f8;--noc-text-secondary:#aab5bf;--noc-healthy:#36c96b;--noc-warning:#f6c344;--noc-degraded:#ff8b3d;--noc-critical:#e53935;--noc-unknown:#7b8791;--noc-accent:#4da3ff;--noc-radius:12px}
.shell{box-sizing:border-box;width:100%;padding:8px 12px;border:1px solid var(--noc-border);border-radius:var(--noc-radius);overflow:hidden;overflow-anchor:none;background:var(--noc-background);color:var(--noc-text-primary);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);box-shadow:0 4px 16px #0004}
h1,h2,p{margin:0}
.mission{display:flex;align-items:center;justify-content:space-between;min-height:50px;gap:12px;padding:6px 10px;border:1px solid var(--noc-border);border-radius:var(--noc-radius);background:var(--noc-panel)}
.mission>div:first-child{min-width:0}
.mission-title,.network-state,.repeater-title,.row,.battery-line{display:flex;align-items:center;gap:7px}
.mission-title{min-width:0}
.mission-title ha-icon{flex:0 0 auto;color:var(--noc-accent);--mdc-icon-size:25px}
.mission h1{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:clamp(1.08rem,1.4vw,1.55rem);line-height:1.05}
.meta{display:flex;min-width:0;gap:4px 14px;margin-top:3px;overflow:hidden;color:var(--noc-text-secondary);font-size:clamp(.72rem,.76vw,.82rem);white-space:nowrap}
.meta span{overflow:hidden;text-overflow:ellipsis}
.network-state{flex:0 0 auto;padding:5px 10px;border-radius:999px;background:var(--noc-panel-alt);font-size:.88rem;font-weight:800;text-transform:uppercase}
.network-state b{font-size:1.08rem}
.status-dot{width:11px;height:11px;flex:0 0 auto;border-radius:50%;background:currentColor}
.kpis{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px;margin-top:7px}
.metric,.repeater,.alert,.empty{box-sizing:border-box;min-width:0;background:var(--noc-panel);border:1px solid var(--noc-border);border-radius:var(--noc-radius)}
.metric{height:68px;padding:6px 9px;overflow:hidden}
.metric-label{display:flex;align-items:center;gap:5px;overflow:hidden;color:var(--noc-text-secondary);font-size:clamp(.62rem,.63vw,.7rem);text-transform:uppercase;letter-spacing:.035em;white-space:nowrap}
.metric-label span{overflow:hidden;text-overflow:ellipsis}
.metric-label ha-icon{flex:0 0 auto;--mdc-icon-size:15px;color:var(--noc-accent)}
.metric b{display:block;margin-top:3px;font-size:clamp(1.2rem,1.45vw,1.65rem);line-height:1}
.metric-context{display:block;margin-top:2px;overflow:hidden;color:var(--noc-text-secondary);font-size:.66rem;text-overflow:ellipsis;white-space:nowrap}
.metric.clock-metric{border-left:4px solid currentColor}
.metric.clock-metric b{color:currentColor;font-size:clamp(.95rem,1.15vw,1.3rem)}
.grid{display:grid;grid-template-columns:repeat(var(--noc-grid-columns,4),minmax(0,1fr));gap:4px;margin-top:5px}
.repeater{padding:5px 8px;border-left:4px solid currentColor;background:var(--noc-panel-alt)}
.repeater-title{justify-content:space-between;min-width:0}
.repeater-title .mission-title{overflow:hidden}
.repeater-title h2{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.92rem}
.repeater-title ha-icon{flex:0 0 auto;--mdc-icon-size:19px}
.badge{display:flex;align-items:center;gap:4px;flex:0 0 auto;padding:2px 6px;border-radius:999px;background:#0003;font-size:.65rem;font-weight:800;text-transform:uppercase}
.badge .status-dot{width:9px;height:9px}
.battery-line{margin-top:4px}
.battery-line ha-icon{--mdc-icon-size:18px}
.battery-track{height:11px;flex:1;overflow:hidden;border:1px solid #ffffff14;border-radius:999px;background:#ffffff12}
.battery-fill{height:100%;border-radius:inherit;background:currentColor;transition:width .2s ease}
.battery-value{min-width:42px;text-align:right;font-size:.92rem;font-weight:800;font-variant-numeric:tabular-nums}
.row{justify-content:space-between;margin-top:2px;color:var(--noc-text-secondary);font-size:.75rem}
.row span{min-width:0}
.row span:last-child{overflow:hidden;color:var(--noc-text-primary);font-weight:650;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}
.row ha-icon{--mdc-icon-size:14px}
.healthy,.fresh{color:var(--noc-healthy)}
.warning,.aging{color:var(--noc-warning)}
.degraded,.stale{color:var(--noc-degraded)}
.critical,.offline,.unhealthy{color:var(--noc-critical)}
.unknown{color:var(--noc-unknown)}
.alerts{display:grid;grid-template-columns:auto repeat(auto-fit,minmax(180px,1fr));align-items:center;gap:6px;padding:6px 9px}
.alerts h2{font-size:.85rem;white-space:nowrap}
.alert{padding:5px 8px;border-left:3px solid var(--noc-critical);overflow:hidden;font-size:.76rem;text-overflow:ellipsis;white-space:nowrap}
.network-summary{color:var(--noc-text-secondary);font-size:.72rem}
.clock-panel{display:grid;grid-template-columns:minmax(150px,1.2fr) repeat(5,minmax(64px,.55fr)) minmax(180px,1.25fr);gap:6px;margin-top:6px;padding:7px 9px;border:1px solid var(--noc-border);border-radius:var(--noc-radius);background:var(--noc-panel)}
.clock-strip-title{grid-column:1/-1;display:flex;align-items:center;gap:6px;font-size:.82rem;font-weight:800}.clock-strip-title ha-icon{--mdc-icon-size:18px;color:var(--noc-accent)}
.clock-cell{min-width:0;color:var(--noc-text-secondary);font-size:.68rem}
.clock-cell b{display:block;overflow:hidden;margin-top:2px;color:var(--noc-text-primary);font-size:.82rem;text-overflow:ellipsis;white-space:nowrap}
.clock-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px}
.clock-action{padding:6px 9px;border:1px solid var(--noc-border);border-radius:8px;background:var(--noc-panel-alt);color:var(--noc-text-primary);cursor:pointer;font:inherit;font-size:.72rem;font-weight:700}
.clock-action:disabled{opacity:.42;cursor:not-allowed}
.clock-action.primary{border-color:var(--noc-accent);background:#1876c9;color:#fff}
.clock-health{display:flex;gap:7px;flex-wrap:wrap;margin-top:5px;color:var(--noc-text-secondary);font-size:.7rem}
.fleet-detail{grid-column:1/-1;border-top:1px solid var(--noc-border);font-size:.7rem}
.fleet-detail summary{padding-top:4px;cursor:pointer;color:var(--noc-text-primary);font-weight:700}
.fleet-detail ul{margin:4px 0 0;padding-left:20px}
.action-feedback{min-height:17px;margin-top:4px;padding:2px 8px;border-left:3px solid var(--noc-accent);color:var(--noc-text-secondary);font-size:.72rem}
.action-feedback.error{border-color:var(--noc-critical);color:#ffb5b3}
.clock-detail{margin-top:3px;border-top:1px solid var(--noc-border);color:var(--noc-text-secondary);font-size:.72rem}
.clock-detail summary{padding-top:4px;cursor:pointer;color:var(--noc-text-primary);font-weight:700}
.clock-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 10px;padding-top:3px}
.clock-detail .clock-action{margin-top:5px}
.empty{padding:18px;text-align:center}
.empty a{color:var(--noc-accent)}
.shell[data-layout="compact"] .repeater{padding-block:4px}
.shell[data-layout="compact"] .row{margin-top:1px}
.shell[data-layout="constrained"]{padding:6px 8px}
.shell[data-layout="constrained"] .mission{align-items:flex-start}
.shell[data-layout="constrained"] .kpis{grid-template-columns:repeat(4,minmax(0,1fr))}
.shell[data-layout="constrained"] .metric{height:62px}
@container(max-width:700px){.mission{display:block}.network-state{display:inline-flex;margin-top:6px}.meta{flex-wrap:wrap;white-space:normal}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.alerts{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.clock-panel{grid-template-columns:repeat(2,minmax(0,1fr))}.clock-actions{justify-content:flex-start}.clock-detail-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.battery-fill{transition:none}}
</style><section class="shell"></section>`;
        this.shadowRoot
          .querySelector(".shell")
          ?.addEventListener("click", (event) => this._handleAction(event));
      }
      refreshOverviewCard(this, "config-initialization");
    }
    set hass(hass) {
      this._hass = hass;
      refreshOverviewCard(this, "hass-state-update");
    }
    getCardSize() {
      return this._config?.section === "alerts" ? 1 : 7;
    }
    _element(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = String(text);
      return element;
    }
    _icon(icon) {
      const element = this._element("ha-icon");
      element.setAttribute("icon", icon);
      return element;
    }
    _value(entityId, fallback = "—") {
      const state = stateValue(this._hass, entityId);
      if (!state || ["unknown", "unavailable"].includes(state.state))
        return fallback;
      const unit = state.attributes?.unit_of_measurement;
      return `${state.state}${unit ? ` ${unit}` : ""}`;
    }
    _addRow(container, icon, label, value, status) {
      const row = this._element("div", "row");
      const heading = this._element("span");
      heading.append(this._icon(icon), document.createTextNode(label));
      row.append(heading, this._element("span", status || "", value));
      container.append(row);
    }
    _actionButton(label, entityId, options = {}) {
      const pending = this._pendingActions?.has(entityId);
      const button = this._element(
        "button",
        `clock-action${options.primary ? " primary" : ""}`,
        pending ? options.pendingLabel || "Working…" : label,
      );
      button.type = "button";
      button.disabled = Boolean(options.disabled || pending || !entityId);
      if (entityId) {
        button.dataset.entityId = entityId;
        button.dataset.actionKind = options.kind || "clock";
        if (options.targetName) button.dataset.targetName = options.targetName;
      }
      return button;
    }
    async _handleAction(event) {
      const button = event.target?.closest?.("[data-entity-id]");
      if (!button || button.disabled) return;
      const entityId = button.dataset.entityId;
      const kind = button.dataset.actionKind;
      const targetName = button.dataset.targetName;
      this._pendingActions = this._pendingActions || new Set();
      this._pendingActions.add(entityId);
      const requestedMessage = actionRequestMessage(kind, targetName);
      this._showFeedback(requestedMessage);
      this._render("clock-action-requested");
      try {
        if (!this._hass?.callService)
          throw new Error("Home Assistant action service unavailable");
        await this._hass.callService("button", "press", {
          entity_id: entityId,
        });
        if (kind === "repeater") {
          const repeater = discoverRepeaters({
            ...this._hass,
            devices: this._config.registry_devices,
            entities: this._config.registry_entities,
          }).find((item) => item.entities.checkClock === entityId);
          const outcome = String(
            stateValue(this._hass, repeater?.entities.clockStatus)?.attributes
              ?.last_clock_attempt_outcome || "",
          );
          const completionMessage = clockCompletionMessage(outcome, targetName);
          if (completionMessage) this._showFeedback(completionMessage);
        }
      } catch (error) {
        this._showFeedback(
          `Action failed: ${error?.message || "request rejected"}`,
          true,
        );
      } finally {
        this._pendingActions.delete(entityId);
        this._render("clock-action-completed");
      }
    }
    _showFeedback(message, error = false) {
      this._actionMessage = message;
      this._actionMessageError = error;
      if (this._feedbackTimer) clearTimeout(this._feedbackTimer);
      this._feedbackTimer = setTimeout(() => {
        this._actionMessage = null;
        this._actionMessageError = false;
        this._render("clock-action-feedback-cleared");
      }, 4500);
    }
    _fleetClockSection(fleet, repeaters) {
      const metrics = fleetClockMetrics(this._hass, fleet);
      const sync = fleetSyncMetrics(this._hass, fleet);
      const controls = fleetControlState(metrics, sync);
      const section = this._element("section", "clock-panel");
      section.setAttribute("aria-label", "Clock Management");
      const heading = this._element("div", "clock-strip-title");
      heading.append(
        this._icon("mdi:clock-check-outline"),
        document.createTextNode("Clock Management"),
      );
      section.append(heading);
      const warning = this._element(
        "div",
        "clock-health warning",
        "Repeaters are synchronised to the connected MeshCore companion clock. Ensure the companion clock is correct before enabling automatic synchronisation.",
      );
      warning.style.gridColumn = "1 / -1";
      section.append(warning);
      const cells = [
        ["Clock State", this._value(fleet.state, "Idle")],
        ["Progress", this._value(fleet.progress, "0/0")],
        [
          "Running",
          normalized(stateValue(this._hass, fleet.running)) === "on"
            ? "Yes"
            : "No",
        ],
        ["Current", metrics.currentRepeater],
        [
          "Position",
          metrics.active && metrics.total
            ? `${metrics.currentIndex} of ${metrics.total}`
            : "—",
        ],
        [
          "Next Check",
          metrics.lifecycle === "waiting"
            ? formatDateTime(metrics.nextCheckAt)
            : metrics.active
              ? "Waiting for reply"
              : "—",
        ],
        ["Completed", metrics.completed],
        ["Success", metrics.success],
        ["Timeout", metrics.timeout],
        ["Failed", metrics.failure],
        ["Remaining", metrics.remaining],
        [
          "Last Fleet Check",
          formatDateTime(stateValue(this._hass, fleet.lastCheck)?.state),
        ],
        [
          "Last Fleet Sync",
          formatDateTime(stateValue(this._hass, fleet.lastSync)?.state),
        ],
        ["Fleet Sync State", sync.lifecycle],
        ["Sync Progress", `${sync.completed} of ${sync.total} repeaters completed`],
        ["Sync Current", sync.currentRepeater],
        ["Sync Successful", sync.successful],
        ["Already Ahead", sync.alreadyAhead],
        ["Sync Failed", sync.failed],
        ["Next Automatic Sync", formatDateTime(sync.nextAutomaticSync)],
        ["Automatic Sync", sync.automaticEnabled ? "Enabled" : "Disabled"],
        ["Sync Interval", `${sync.interval} hours`],
        ["Next Scheduled", formatDateTime(metrics.nextScheduledRun)],
        ["Automatic", metrics.automaticEnabled ? "Enabled" : "Disabled"],
      ];
      for (const [label, value] of cells) {
        const cell = this._element("div", "clock-cell", label);
        cell.append(this._element("b", "", value));
        section.append(cell);
      }
      const actions = this._element("div", "clock-actions");
      actions.append(
        this._actionButton("Check All Clocks", fleet.checkAll, {
          disabled: controls.checkAllDisabled,
          kind: "fleet",
          pendingLabel: "Starting…",
          primary: true,
        }),
        this._actionButton("Synchronise All Clocks", fleet.syncAll, {
          disabled: controls.syncAllDisabled,
          kind: "fleet-sync",
          pendingLabel: "Synchronising…",
          primary: true,
        }),
        this._actionButton("Cancel Check", fleet.cancel, {
          disabled: controls.cancelDisabled,
          kind: "cancel",
          pendingLabel: "Cancelling…",
        }),
      );
      section.append(actions);
      const health = this._element("div", "clock-health");
      health.style.gridColumn = "1 / -1";
      health.append(
        document.createTextNode(
          `Fleet clock health · In Sync ${metrics.health.inSync} · Minor ${metrics.health.minorDrift} · Drift ${metrics.health.drift} · Critical ${metrics.health.critical} · Unknown ${metrics.health.unknown}`,
        ),
      );
      const attention = [
        ...metrics.health.driftRepeaters,
        ...metrics.health.criticalRepeaters,
      ];
      if (attention.length)
        health.title = `Drift or Critical: ${attention.join(", ")}`;
      section.append(health);
      if (
        ["completed", "completed with errors", "completed_with_errors"].includes(
          metrics.lifecycle,
        )
      ) {
        const completed = this._element("div", "clock-health");
        completed.style.gridColumn = "1 / -1";
        completed.append(
          document.createTextNode(
            `Completed ${formatDateTime(metrics.completedAt)} · Duration ${
              metrics.totalDurationSeconds == null
                ? "—"
                : `${Math.round(metrics.totalDurationSeconds)} s`
            } · Success ${metrics.success} · Timeout ${metrics.timeout} · Failed ${metrics.failure}`,
          ),
        );
        section.append(completed);
      }
      if (metrics.failedRepeaters.length) {
        const failures = this._element("details", "fleet-detail");
        failures.append(
          this._element(
            "summary",
            "",
            `${metrics.failedRepeaters.length} failed or timed-out repeater${
              metrics.failedRepeaters.length === 1 ? "" : "s"
            }`,
          ),
        );
        const list = this._element("ul");
        for (const failure of metrics.failedRepeaters)
          list.append(
            this._element(
              "li",
              "",
              `${failure.name}: ${failure.outcome}${
                failure.error ? ` · ${failure.error}` : ""
              }`,
            ),
          );
        failures.append(list);
        section.append(failures);
      }
      const results = this._element("div", "clock-health");
      results.style.gridColumn = "1 / -1";
      results.append(this._element("b", "", "Managed repeater clock results"));
      for (const repeater of repeaters) {
        const clock = stateValue(this._hass, repeater.entities.clockStatus);
        const attributes = clock?.attributes || {};
        const syncResult = sync.perRepeater.find(
          (item) => item.stable_id === repeater.stableId,
        );
        const result = syncResult?.result || attributes.last_sync_result || "never";
        const detail =
          syncResult?.remote_response ||
          syncResult?.error ||
          attributes.last_sync_response ||
          attributes.last_sync_error ||
          "No sync result";
        const row = this._element(
          "div",
          `clock-result-row ${String(result).toLowerCase()}`,
          `${repeater.name} · ${signedClockOffset(
            this._hass,
            repeater.entities.clockOffset,
          )} · check ${attributes.last_clock_attempt_outcome || "never"} · sync ${result} · ${formatDateTime(
            attributes.last_sync_time,
          )} · ${detail}`,
        );
        row.prepend(
          this._icon(
            ["success", "already_ahead"].includes(String(result))
              ? "mdi:check-circle"
              : ["failed", "timeout", "unauthorized"].includes(String(result))
                ? "mdi:alert-circle"
                : String(result) === "running"
                  ? "mdi:progress-clock"
                  : "mdi:clock-outline",
          ),
        );
        results.append(row);
      }
      section.append(results);
      return section;
    }
    _repeaterCard(repeater, fleetMetrics) {
      const card = this._element("article", "repeater");
      const status = repeaterStatus(this._hass, repeater);
      card.classList.add(status.label);
      const title = this._element("div", "repeater-title");
      const name = this._element("h2", "", repeater.name);
      name.title = repeater.name;
      const identity = this._element("span", "mission-title");
      identity.append(this._icon("mdi:access-point"), name);
      const badge = this._element("span", `badge ${status.label}`);
      badge.setAttribute("aria-label", `Status ${status.label}`);
      badge.append(
        this._element("span", "status-dot"),
        document.createTextNode(status.label),
      );
      title.append(identity, badge);
      card.append(title);

      const battery = clampBattery(
        numericState(this._hass, repeater.entities.battery),
      );
      const batteryClass =
        battery === null
          ? "unknown"
          : battery < 15
            ? "critical"
            : battery < 30
              ? "warning"
              : status.label;
      const batteryLine = this._element("div", `battery-line ${batteryClass}`);
      batteryLine.append(this._icon("mdi:battery"));
      const track = this._element("div", "battery-track");
      const fill = this._element("div", "battery-fill");
      fill.style.width = battery === null ? "0" : `${battery}%`;
      track.append(fill);
      batteryLine.append(
        track,
        this._element(
          "span",
          "battery-value",
          battery === null ? "—" : `${Math.round(battery)}%`,
        ),
      );
      card.append(batteryLine);
      this._addRow(
        card,
        "mdi:lightning-bolt",
        "Voltage",
        this._value(repeater.entities.voltage),
      );
      this._addRow(
        card,
        "mdi:heart-pulse",
        "Health",
        this._value(repeater.entities.health),
        status.health,
      );
      this._addRow(
        card,
        "mdi:clock-outline",
        "Freshness",
        formatAge(repeaterAgeSeconds(this._hass, repeater)),
        status.label,
      );
      const clockState = stateValue(this._hass, repeater.entities.clockStatus);
      const clock = clockStatusPresentation(clockState?.state);
      const attributes = clockState?.attributes || {};
      const clockAged =
        Number(attributes.clock_data_age_seconds) > 6 * 60 * 60;
      this._addRow(
        card,
        clock.icon,
        "Clock",
        `${clock.label}${clockAged ? " (aged)" : ""} · ${signedClockOffset(
          this._hass,
          repeater.entities.clockOffset,
        )}`,
        clockAged && clock.className === "healthy"
          ? "warning"
          : clock.className,
      );
      const details = this._element("details", "clock-detail");
      details.append(this._element("summary", "", "Clock details"));
      const detailGrid = this._element("div", "clock-detail-grid");
      const detailRows = [
        ["Clock status", clock.label],
        [
          "Clock offset",
          signedClockOffset(this._hass, repeater.entities.clockOffset),
        ],
        [
          "Last successful",
          formatDateTime(attributes.last_successful_clock_check),
        ],
        ["Last attempt", formatDateTime(attributes.last_clock_attempt)],
        ["Outcome", attributes.last_clock_attempt_outcome || "—"],
        [
          "RTT",
          attributes.clock_rtt_ms == null
            ? "—"
            : `${attributes.clock_rtt_ms} ms`,
        ],
        ["Response", attributes.response_text || "—"],
        ["Sender timestamp", attributes.sender_timestamp ?? "—"],
        ["Error", attributes.last_clock_attempt_error || "—"],
        [
          "Data age",
          attributes.clock_data_age_seconds == null
            ? "—"
            : formatAge(Number(attributes.clock_data_age_seconds)),
        ],
        [
          "History",
          `${Array.isArray(attributes.check_history) ? attributes.check_history.length : 0} retained attempts`,
        ],
      ];
      for (const [label, value] of detailRows) {
        const cell = this._element("div", "clock-cell", label);
        cell.append(this._element("b", "", value));
        detailGrid.append(cell);
      }
      const busy = repeaterClockBusy(this._hass, repeater, fleetMetrics);
      details.append(
        detailGrid,
        this._actionButton("Check Clock", repeater.entities.checkClock, {
          disabled: busy,
          kind: "repeater",
          targetName: repeater.name,
          pendingLabel: "Checking…",
          primary: true,
        }),
      );
      card.append(details);
      return card;
    }
    async _ensureVersion() {
      if (this._manifestRequested) return;
      const installedVersion = installedVersionFromState(
        this._hass,
        this._config?.registry_entities,
      );
      if (installedVersion) {
        this._version = installedVersion;
        return;
      }
      if (!this._hass?.callWS) return;
      this._manifestRequested = true;
      try {
        const manifest = await this._hass.callWS({
          type: "manifest/get",
          integration: DOMAIN,
        });
        this._version = manifest?.version || null;
      } catch (_error) {
        this._version = null;
      }
      this._render("manifest-version-update");
    }
    _render(reason = "unspecified") {
      const shell = this.shadowRoot?.querySelector(".shell");
      if (!this.isConnected || !shell || !this._hass || !this._config) return;
      const scrollSnapshot = scrollSnapshotForRender(
        this,
        this._hasRendered,
      );
      const repeaters = discoverRepeaters({
        ...this._hass,
        devices: this._config.registry_devices,
        entities: this._config.registry_entities,
      });
      const fleetClock = discoverFleetClock({
        ...this._hass,
        entities: this._config.registry_entities,
      });
      const structureKey = overviewStructureKey(this._config, repeaters);
      const structuralChange = !canReconcileOverview(
        this._hasRendered,
        this._structureKey,
        structureKey,
        shell,
      );
      const renderShell = structuralChange
        ? shell
        : document.createElement("section");
      if (structuralChange) shell.replaceChildren();
      shell.dataset.count = String(repeaters.length);
      this._applyResponsiveLayout(repeaters.length);
      const metrics = networkMetrics(this._hass, repeaters);
      const clockFleetMetrics = fleetClockMetrics(this._hass, fleetClock);
      const clockTile = clockSummaryTile(clockFleetMetrics.health);
      if (this._config.section === "alerts") {
        const alertSection = this._element("section", "alerts");
        alertSection.append(this._element("h2", "", "Active alerts"));
        const alerts = metrics.statuses.filter(({ alert }) => alert);
        if (!alerts.length)
          alertSection.append(
            this._element("div", "alert healthy", "No active alerts"),
          );
        for (const { repeater, alertReason } of alerts) {
          const alert = this._element(
            "div",
            "alert",
            `${repeater.name}: ${alertReason}`,
          );
          alert.title = `${repeater.name}: ${alertReason}`;
          alertSection.append(alert);
        }
        if (metrics.oldestUpdateRepeater)
          alertSection.append(
            this._element(
              "div",
              "network-summary",
              `Oldest update: ${formatAge(metrics.oldestUpdate)} · ${metrics.oldestUpdateRepeater.name}`,
            ),
          );
        renderShell.append(alertSection);
        this._finishRender(
          scrollSnapshot,
          shell,
          renderShell,
          structureKey,
          structuralChange,
          reason,
        );
        return;
      }
      const head = this._element("header", "mission");
      const title = this._element("div");
      const titleLine = this._element("div", "mission-title");
      titleLine.append(
        this._icon("mdi:access-point-network"),
        this._element("h1", "", "MeshCore Network Operations Centre"),
      );
      const ages = repeaters
        .map((repeater) => repeaterAgeSeconds(this._hass, repeater))
        .filter(Number.isFinite);
      const meta = this._element("div", "meta");
      meta.append(
        this._element("span", "", `Version ${this._version || "—"}`),
        this._element(
          "span",
          "",
          `Updated ${formatAge(ages.length ? Math.min(...ages) : null)}`,
        ),
        this._element(
          "span",
          "",
          `${metrics.managed} managed repeater${metrics.managed === 1 ? "" : "s"}`,
        ),
      );
      title.append(titleLine, meta);
      const state = overallState(metrics.health);
      const network = this._element("div", `network-state ${state}`);
      network.append(
        this._element("span", "status-dot"),
        document.createTextNode(state),
        this._element(
          "b",
          "",
          metrics.health === null ? "—" : `${metrics.health}%`,
        ),
      );
      head.append(title, network);
      renderShell.append(head);
      if (!repeaters.length) {
        const empty = this._element("div", "empty");
        empty.append(
          this._element("h2", "", "No managed repeaters selected"),
          this._element(
            "p",
            "muted",
            "Open MeshCore NOC integration options to select repeaters.",
          ),
        );
        const link = this._element("a", "", "Open integration configuration");
        link.href = "/config/integrations/integration/meshcore_noc";
        empty.append(link);
        renderShell.append(empty);
        this._finishRender(
          scrollSnapshot,
          shell,
          renderShell,
          structureKey,
          structuralChange,
          reason,
        );
        return;
      }
      const kpis = [
        ["Managed", "mdi:access-point-network", metrics.managed, ""],
        ["Online", "mdi:lan-connect", metrics.online, ""],
        [
          "Offline",
          "mdi:lan-disconnect",
          metrics.offline,
          metrics.statuses.find(({ label }) => label === "offline")?.repeater
            .name || "",
        ],
        [
          "Alerts",
          "mdi:alert-outline",
          metrics.alerts,
          metrics.firstAlert
            ? `${metrics.firstAlert.repeater.name}: ${metrics.firstAlert.alertReason}`
            : "No active alerts",
        ],
        [
          "Average Battery",
          "mdi:battery-medium",
          metrics.averageBattery === null
            ? "—"
            : `${Math.round(metrics.averageBattery)}%`,
          "",
        ],
        [
          "Lowest Battery",
          "mdi:battery-low",
          metrics.lowestBattery === null
            ? "—"
            : `${Math.round(metrics.lowestBattery)}%`,
          metrics.lowestBatteryRepeater?.name || "",
        ],
        [
          "Clock",
          "mdi:clock-check-outline",
          clockTile.value,
          clockTile.context,
          clockTile.severity,
        ],
        [
          "Network Health",
          "mdi:heart-pulse",
          metrics.health === null ? "—" : `${metrics.health}%`,
          "",
        ],
      ];
      const summary = this._element("section", "kpis");
      for (const [label, icon, value, context, severity] of kpis) {
        const metric = this._element(
          "div",
          `metric${label === "Clock" ? ` clock-metric ${severity}` : ""}`,
        );
        const metricLabel = this._element("span", "metric-label");
        metricLabel.append(
          this._icon(icon),
          this._element("span", "", label),
        );
        metric.append(
          metricLabel,
          this._element("b", "", value),
        );
        if (context) {
          const metricContext = this._element(
            "span",
            "metric-context",
            context,
          );
          metricContext.title = context;
          metric.append(metricContext);
        }
        summary.append(metric);
      }
      renderShell.append(summary);
      if (Object.keys(fleetClock).length)
        renderShell.append(this._fleetClockSection(fleetClock, repeaters));
      if (this._actionMessage)
        renderShell.append(
          this._element(
            "div",
            `action-feedback${this._actionMessageError ? " error" : ""}`,
            this._actionMessage,
          ),
        );
      const grid = this._element("section", "grid");
      for (const repeater of repeaters)
        grid.append(this._repeaterCard(repeater, clockFleetMetrics));
      renderShell.append(grid);
      this._finishRender(
        scrollSnapshot,
        shell,
        renderShell,
        structureKey,
        structuralChange,
        reason,
      );
    }
    _finishRender(
      scrollSnapshot,
      shell,
      renderShell,
      structureKey,
      structuralChange,
      reason,
    ) {
      if (!structuralChange) reconcileChildren(shell, renderShell);
      this._structureKey = structureKey;
      this._hasRendered = true;
      restoreScrollPosition(scrollSnapshot);
    }
    _applyResponsiveLayout(repeaterCount) {
      const shell = this.shadowRoot?.querySelector(".shell");
      if (!shell) return;
      const width =
        this.getBoundingClientRect?.().width || globalThis.innerWidth || 0;
      const height = globalThis.innerHeight || 0;
      const layout = responsiveLayout(width, height, repeaterCount);
      shell.dataset.layout = layout.density;
      shell.style.setProperty("--noc-grid-columns", String(layout.columns));
    }
    _ensureResponsiveLayout() {
      if (
        this._resizeObserver ||
        typeof globalThis.ResizeObserver === "undefined"
      )
        return;
      this._resizeObserver = new globalThis.ResizeObserver(() => {
        const count = Number(
          this.shadowRoot?.querySelector(".shell")?.dataset.count || 0,
        );
        this._applyResponsiveLayout(count);
      });
      this._resizeObserver.observe(this);
    }
    _ensureRegistrySubscriptions() {
      if (this._subscriptions || !this._hass?.connection?.subscribeEvents)
        return;
      this._subscriptions = ["device_registry_updated", "entity_registry_updated"].map(
        (eventType) =>
          this._hass.connection.subscribeEvents(() => {
            if (!this._registryReloadPending) {
              this._registryReloadPending = true;
              window.location.reload();
            }
          }, eventType),
      );
    }
    connectedCallback() {
      refreshOverviewCard(this, "connected");
    }
    disconnectedCallback() {
      this._resizeObserver?.disconnect();
      this._resizeObserver = null;
      if (this._feedbackTimer) clearTimeout(this._feedbackTimer);
      this._feedbackTimer = null;
      for (const unsubscribe of this._subscriptions || [])
        Promise.resolve(unsubscribe).then((callback) => callback());
      this._subscriptions = null;
    }
  }
  const registerStrategy = (targetWindow, registry) => {
    if (!registry.get("ll-strategy-dashboard-meshcore-noc"))
      registry.define(
        "ll-strategy-dashboard-meshcore-noc",
        MeshCoreNocDashboardStrategy,
      );
    if (!registry.get("meshcore-noc-overview-card"))
      registry.define("meshcore-noc-overview-card", MeshCoreNocOverviewCard);
    targetWindow.customStrategies = targetWindow.customStrategies || [];
    if (
      !targetWindow.customStrategies.some(
        (item) =>
          item.type === STRATEGY_PICKER_TYPE &&
          item.strategyType === "dashboard",
      )
    )
      targetWindow.customStrategies.push({
        type: STRATEGY_PICKER_TYPE,
        name: "MeshCore NOC",
        description:
          "Dynamic Network Operations Centre dashboard for managed MeshCore repeaters",
        strategyType: "dashboard",
        icon: "mdi:access-point-network",
      });
  };
  if (typeof window !== "undefined" && typeof customElements !== "undefined")
    registerStrategy(window, customElements);
  if (typeof module !== "undefined")
    module.exports = {
      clampBattery,
      actionRequestMessage,
      canReconcileOverview,
      clockSummaryTile,
      clockCompletionMessage,
      clockStatusPresentation,
      discoverFleetClock,
      discoverRepeaters,
      fleetClockMetrics,
      fleetSyncMetrics,
      fleetControlState,
      generateDashboard,
      installedVersionFromState,
      networkMetrics,
      overviewStructureKey,
      overallState,
      registerStrategy,
      repeaterClockBusy,
      repeaterStatus,
      responsiveLayout,
      refreshOverviewCard,
      reconcileChildren,
      restoreScrollPosition,
      safePath,
      scrollContainerFor,
      scrollSnapshotForRender,
      signedClockOffset,
      readableClockOffset,
    };
})();
