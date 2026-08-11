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
  const MANAGEMENT_DEFAULTS = Object.freeze({
    voltage_offset: -0.816,
    empty_voltage: 3.0,
    full_voltage: 4.2,
    battery_warning: 40,
    battery_critical: 20,
    fresh_max_age: 4500,
    aging_max_age: 7200,
    stale_max_age: 10800,
    offline_max_age: 10800,
    clock_warning: 120,
    clock_critical: 300,
    display_name: null,
    password_configured: false,
  });
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
  const shortDisplayName = (name, stableId = "") => {
    const cleaned = String(name || "")
      .replace(/^\s*meshcore(?:\s+(?:noc|repeater|client))?\s*:?\s*/i, "")
      .replace(/\s*\([0-9a-f]{6}\)\s*$/i, "")
      .replace(/\s+/g, " ")
      .trim();
    const withoutGenericSuffix = cleaned.replace(/\s+repeater$/i, "").trim();
    return withoutGenericSuffix || cleaned || stableId || "Managed repeater";
  };
  const stateValue = (hass, entityId) => hass.states?.[entityId];
  const normalized = (state) =>
    state && !["unknown", "unavailable"].includes(state.state)
      ? state.state.toLowerCase()
      : "unknown";
  const operationClass = (value) => {
    const state = String(value || "").toLowerCase();
    if (state.includes("fail") || state.includes("timeout"))
      return "operation-failed";
    if (
      state.includes("running") ||
      state.includes("checking") ||
      state.includes("sync") ||
      state.includes("queued")
    )
      return "operation-running";
    if (
      state.includes("complete") ||
      state.includes("success") ||
      state === "idle"
    )
      return "operation-completed";
    return "value-unknown";
  };
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
      : kind === "repeater-sync"
        ? `Clock synchronisation requested for ${targetName || "managed repeater"}`
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
  const networkAlerts = (hass, metrics) => {
    const alerts = [];
    for (const item of metrics.statuses) {
      const { repeater, label, freshness, battery } = item;
      const clockState = stateValue(hass, repeater.entities.clockStatus);
      const clock = clockStatusPresentation(clockState?.state);
      const clockAttributes = clockState?.attributes || {};
      const name = shortDisplayName(repeater.name, repeater.stableId);
      const target = `/meshcore-noc/${safePath(repeater.stableId)}`;
      let alert = null;
      if (label === "offline") {
        alert = { severity: "critical", icon: "mdi:lan-disconnect", text: `${name} Offline` };
      } else if (Number.isFinite(battery) && battery < 20) {
        alert = { severity: "critical", icon: "mdi:battery-alert", text: `${name} Battery ${Math.round(battery)}%` };
      } else if (freshness === "stale") {
        alert = { severity: "degraded", icon: "mdi:clock-alert-outline", text: `${name} Stale` };
      } else if (Number.isFinite(battery) && battery < 40) {
        alert = { severity: "warning", icon: "mdi:battery-low", text: `${name} Battery ${Math.round(battery)}%` };
      } else if (clock.className === "critical") {
        alert = { severity: "critical", icon: clock.icon, text: `${name} Clock Critical` };
      } else if (["degraded", "warning"].includes(clock.className)) {
        alert = {
          severity: "warning",
          icon: clock.icon,
          text: `${name} Clock ${signedClockOffset(hass, repeater.entities.clockOffset)}`,
        };
      } else if (["failed", "timeout", "malformed"].includes(
        String(clockAttributes.last_clock_attempt_outcome || ""),
      )) {
        alert = { severity: "critical", icon: "mdi:clock-remove-outline", text: `${name} Clock Check Failed` };
      }
      if (alert) alerts.push({ ...alert, stableId: repeater.stableId, target });
    }
    return alerts;
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
  const generateDashboard = (hass) => {
    const repeaters = discoverRepeaters(hass);
    const registry = {
      registry_devices: values(hass.devices),
      registry_entities: values(hass.entities),
    };
    const views = [
      {
        title: "Mission Control",
        path: "network",
        icon: "mdi:access-point-network",
        panel: true,
        cards: [
          {
            type: "custom:meshcore-noc-overview-card",
            section: "operations",
            ...registry,
          },
        ],
      },
    ];
    for (const repeater of repeaters) {
      views.push({
        title: shortDisplayName(repeater.name, repeater.stableId),
        path: safePath(repeater.stableId),
        icon: "mdi:access-point",
        subview: true,
        panel: true,
        cards: [
          {
            type: "custom:meshcore-noc-overview-card",
            section: "detail",
            stable_id: repeater.stableId,
            ...registry,
          },
        ],
      });
    }
    return {
      title: "MeshCore NOC",
      views,
    };
  };
  class MeshCoreNocHistoryChart extends HTMLElementBase {
    setConfig(config) {
      const nextKey = JSON.stringify(config || {});
      if (this._configKey === nextKey) return;
      this._configKey = nextKey;
      this._config = config || {};
      this._rangeHours = Number(this._config.hours || 24);
      if (!this.shadowRoot) {
        this.attachShadow({ mode: "open" });
        this.shadowRoot.innerHTML = `<style>
:host{display:block;min-width:0}
.chart{box-sizing:border-box;min-height:360px;padding:14px;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:#1a2128;color:#f3f6f8;font-family:system-ui,sans-serif}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
h2{margin:0;font-size:1rem}.subtitle{margin-top:3px;color:#aab5bf;font-size:.72rem}
.ranges{display:flex;gap:4px}.ranges button{padding:5px 9px;border:1px solid rgba(255,255,255,.12);border-radius:7px;background:#202832;color:#f3f6f8;cursor:pointer;font:inherit;font-size:.7rem;font-weight:700}.ranges button[aria-pressed="true"]{border-color:#4da3ff;background:#1876c9}
.plot{position:relative;min-height:280px}.plot svg{display:block;width:100%;height:280px;overflow:visible}
.grid-line{stroke:rgba(255,255,255,.08);stroke-width:1}.axis-label{fill:#aab5bf;font-size:10px}.series{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.legend{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px;color:#aab5bf;font-size:.68rem}.legend span{display:flex;align-items:center;gap:5px}.swatch{width:9px;height:9px;border-radius:50%}
.empty{display:grid;min-height:260px;place-items:center;color:#aab5bf;text-align:center}.error{color:#ffb5b3}
@container(max-width:700px){.chart{min-height:320px;padding:10px}header{display:block}.ranges{margin-top:8px}.plot svg{height:240px}}
</style><section class="chart"><header><div><h2></h2><div class="subtitle">Calibrated voltage · Recorder history · invalid and negative values excluded</div></div><div class="ranges" aria-label="History range"><button data-hours="24">24 h</button><button data-hours="168">7 d</button><button data-hours="720">30 d</button></div></header><div class="plot"><div class="empty">Loading voltage history…</div></div><div class="legend"></div></section>`;
        this.shadowRoot
          .querySelector(".ranges")
          ?.addEventListener("click", (event) => {
            const button = event.target?.closest?.("[data-hours]");
            if (!button) return;
            this._rangeHours = Number(button.dataset.hours);
            this._lastLoadAt = 0;
            this._load();
          });
      }
      this._renderRange();
      this._load();
    }
    set hass(hass) {
      this._hass = hass;
      this._load();
    }
    connectedCallback() {
      this._load();
    }
    _renderRange() {
      for (const button of this.shadowRoot?.querySelectorAll("[data-hours]") || [])
        button.setAttribute(
          "aria-pressed",
          String(Number(button.dataset.hours) === this._rangeHours),
        );
      const title = this.shadowRoot?.querySelector("h2");
      if (title) title.textContent = this._config?.title || "Fleet voltage";
    }
    async _load() {
      if (!this.isConnected || !this._hass?.callApi || !this._config) return;
      if (Date.now() - (this._lastLoadAt || 0) < 60_000) return;
      this._lastLoadAt = Date.now();
      const series = (this._config.series || []).filter(
        (item) => item?.entity && item?.name,
      );
      this._renderRange();
      if (!series.length) {
        this._renderMessage("No calibrated voltage entities are available.");
        return;
      }
      const requestId = (this._requestId || 0) + 1;
      this._requestId = requestId;
      this._renderMessage("Loading voltage history…");
      const start = new Date(Date.now() - this._rangeHours * 60 * 60 * 1000);
      const query = new URLSearchParams({
        filter_entity_id: series.map((item) => item.entity).join(","),
        minimal_response: "",
        no_attributes: "",
        significant_changes_only: "0",
      });
      try {
        const history = await this._hass.callApi(
          "GET",
          `history/period/${start.toISOString()}?${query.toString()}`,
        );
        if (requestId !== this._requestId) return;
        this._renderHistory(series, Array.isArray(history) ? history : []);
      } catch (error) {
        if (requestId !== this._requestId) return;
        this._renderMessage(
          `Recorder history unavailable: ${error?.message || "request failed"}`,
          true,
        );
      }
    }
    _renderMessage(message, error = false) {
      const plot = this.shadowRoot?.querySelector(".plot");
      const legend = this.shadowRoot?.querySelector(".legend");
      if (plot)
        plot.innerHTML = `<div class="empty${error ? " error" : ""}"></div>`;
      const empty = plot?.querySelector(".empty");
      if (empty) empty.textContent = message;
      if (legend) legend.replaceChildren();
    }
    _renderHistory(series, history) {
      const byEntity = new Map(
        history
          .filter((states) => Array.isArray(states) && states.length)
          .map((states) => [states[0].entity_id, states]),
      );
      const points = series.map((item) => ({
        ...item,
        values: (() => {
          let gapBefore = false;
          const result = [];
          for (const state of byEntity.get(item.entity) || []) {
            const rawTime =
              state.last_changed || state.last_updated || state.lu;
            const numericTime = Number(rawTime);
            const rawValue = state.state ?? state.s;
            const value =
              rawValue === null ||
              rawValue === undefined ||
              rawValue === "" ||
              ["unknown", "unavailable"].includes(
                String(rawValue).toLowerCase(),
              )
                ? Number.NaN
                : Number(rawValue);
            const point = {
              time: Number.isFinite(numericTime)
                ? numericTime < 1_000_000_000_000
                  ? numericTime * 1000
                  : numericTime
                : new Date(rawTime).getTime(),
              value,
              gapBefore,
            };
            if (
              Number.isFinite(point.time) &&
              Number.isFinite(value) &&
              value >= 0 &&
              value <= 10
            ) {
              result.push(point);
              gapBefore = false;
            } else {
              gapBefore = true;
            }
          }
          return result;
        })(),
      }));
      const all = points.flatMap((item) => item.values);
      if (!all.length) {
        this._renderMessage("No valid calibrated voltage history in this range.");
        return;
      }
      const width = 1000;
      const height = 280;
      const pad = { left: 45, right: 14, top: 12, bottom: 28 };
      const minTime = Date.now() - this._rangeHours * 60 * 60 * 1000;
      const maxTime = Date.now();
      const values = all.map((item) => item.value);
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const margin = Math.max(0.05, (rawMax - rawMin) * 0.15);
      const minValue = Math.max(0, Math.floor((rawMin - margin) * 10) / 10);
      const maxValue = Math.ceil((rawMax + margin) * 10) / 10 || minValue + 1;
      const x = (time) =>
        pad.left +
        ((time - minTime) / (maxTime - minTime)) *
          (width - pad.left - pad.right);
      const y = (value) =>
        pad.top +
        ((maxValue - value) / (maxValue - minValue || 1)) *
          (height - pad.top - pad.bottom);
      const colors = [
        "#4da3ff",
        "#36c96b",
        "#f6c344",
        "#ff8b3d",
        "#d77bff",
        "#4dd6c5",
        "#ff6f91",
        "#9cc45b",
      ];
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", `${this._config.title || "Voltage"} history`);
      for (let index = 0; index <= 4; index += 1) {
        const value = minValue + ((maxValue - minValue) * index) / 4;
        const lineY = y(value);
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("class", "grid-line");
        line.setAttribute("x1", String(pad.left));
        line.setAttribute("x2", String(width - pad.right));
        line.setAttribute("y1", String(lineY));
        line.setAttribute("y2", String(lineY));
        svg.append(line);
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("class", "axis-label");
        label.setAttribute("x", "2");
        label.setAttribute("y", String(lineY + 4));
        label.textContent = `${value.toFixed(2)} V`;
        svg.append(label);
      }
      const legend = this.shadowRoot?.querySelector(".legend");
      legend?.replaceChildren();
      points.forEach((item, index) => {
        if (!item.values.length) return;
        const color = colors[index % colors.length];
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("class", "series");
        path.setAttribute("stroke", color);
        path.setAttribute(
          "d",
          item.values
            .map(
              (point, pointIndex) =>
                `${pointIndex && !point.gapBefore ? "L" : "M"}${x(point.time).toFixed(1)},${y(
                  point.value,
                ).toFixed(1)}`,
            )
            .join(" "),
        );
        const tooltip = document.createElementNS("http://www.w3.org/2000/svg", "title");
        const last = item.values[item.values.length - 1];
        tooltip.textContent = `${item.name}: ${last.value.toFixed(3)} V`;
        path.append(tooltip);
        svg.append(path);
        const sampleStep = Math.max(1, Math.ceil(item.values.length / 120));
        item.values.forEach((point, pointIndex) => {
          if (
            pointIndex % sampleStep !== 0 &&
            pointIndex !== item.values.length - 1
          )
            return;
          const hover = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "circle",
          );
          hover.setAttribute("cx", x(point.time).toFixed(1));
          hover.setAttribute("cy", y(point.value).toFixed(1));
          hover.setAttribute("r", "6");
          hover.setAttribute("fill", color);
          hover.setAttribute("fill-opacity", "0");
          const pointTitle = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "title",
          );
          pointTitle.textContent = `${item.name}: ${point.value.toFixed(
            3,
          )} V · ${new Date(point.time).toLocaleString()}`;
          hover.append(pointTitle);
          svg.append(hover);
        });
        const legendItem = document.createElement("span");
        const swatch = document.createElement("i");
        swatch.className = "swatch";
        swatch.style.background = color;
        legendItem.append(swatch, document.createTextNode(item.name));
        legend?.append(legendItem);
      });
      const plot = this.shadowRoot?.querySelector(".plot");
      plot?.replaceChildren(svg);
    }
  }
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
      this._managementSettings = this._managementSettings || new Map();
      this._managementDrafts = this._managementDrafts || new Map();
      this._managementLoads = this._managementLoads || new Set();
      this._managementMessages = this._managementMessages || new Map();
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
.noc-header{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;padding:10px 12px;border:1px solid var(--noc-border);border-radius:var(--noc-radius);background:var(--noc-panel)}
.noc-heading{display:flex;align-items:center;gap:8px}.noc-heading h1{font-size:1.2rem}.noc-heading ha-icon{color:var(--noc-accent)}
.status-line,.clock-line{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:4px;color:var(--noc-text-secondary);font-size:.78rem}.status-line b{color:var(--noc-text-primary);text-transform:capitalize}.clock-line{font-size:.7rem}
.header-alerts{grid-column:1/-1;display:flex;min-height:22px;align-items:center;gap:6px;overflow:auto}.alert-chip{display:inline-flex;align-items:center;gap:4px;flex:0 0 auto;padding:3px 7px;border:1px solid currentColor;border-radius:999px;color:var(--noc-warning);font-size:.68rem;text-decoration:none}.alert-chip.critical{color:var(--noc-critical)}.alert-chip.degraded{color:var(--noc-degraded)}.alert-chip ha-icon{--mdc-icon-size:14px}
.header-controls{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}.header-progress{width:100%;color:var(--noc-text-secondary);font-size:.68rem;text-align:right}.source-warning{grid-column:1/-1;color:var(--noc-text-secondary);font-size:.65rem}
.ops-layout{display:grid;grid-template-columns:minmax(230px,28%) minmax(0,1fr);gap:8px;margin-top:8px}.fleet-list,.detail-panel{min-width:0;padding:9px;border:1px solid var(--noc-border);border-radius:var(--noc-radius);background:var(--noc-panel)}.fleet-list h2,.detail-panel h2{font-size:.88rem}
.fleet-rows{display:grid;gap:4px;margin-top:7px}.fleet-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:7px;padding:7px 8px;border:1px solid transparent;border-left:4px solid currentColor;border-radius:8px;background:var(--noc-panel-alt);color:var(--noc-text-primary);text-decoration:none}.fleet-row:hover,.fleet-row:focus-visible{border-color:var(--noc-accent);outline:none}.fleet-row .status-dot{color:currentColor}.fleet-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:750}.fleet-value{color:var(--noc-text-secondary);font-size:.72rem;font-variant-numeric:tabular-nums}.fleet-state{grid-column:2/-1;color:var(--noc-text-secondary);font-size:.62rem}
.detail-header{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:11px 12px;border:1px solid var(--noc-border);border-left:5px solid currentColor;border-radius:var(--noc-radius);background:var(--noc-panel)}.detail-header h1{font-size:1.35rem}.detail-summary{margin-top:5px;color:var(--noc-text-secondary);font-size:.78rem}.back-link{color:var(--noc-accent);font-size:.72rem;text-decoration:none}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.detail-panel{padding:11px}.detail-panel.wide{grid-column:1/-1}.detail-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:8px}.detail-metric{padding:7px;border-radius:8px;background:var(--noc-panel-alt);color:var(--noc-text-secondary);font-size:.67rem}.detail-metric b{display:block;margin-top:2px;overflow:hidden;color:var(--noc-text-primary);font-size:.84rem;text-overflow:ellipsis;white-space:nowrap}.detail-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.settings-note{margin-top:7px;padding:7px;border-left:3px solid var(--noc-warning);background:var(--noc-panel-alt);color:var(--noc-text-secondary);font-size:.7rem}.advanced{margin-top:8px}.advanced summary{cursor:pointer;font-size:.8rem;font-weight:750}.advanced .detail-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
.management-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:9px}.management-form label{display:grid;gap:3px;color:var(--noc-text-secondary);font-size:.68rem}.management-form input{box-sizing:border-box;width:100%;padding:7px 8px;border:1px solid var(--noc-border);border-radius:7px;background:var(--noc-background);color:var(--noc-text-primary);font:inherit}.management-form input:focus{border-color:var(--noc-accent);outline:2px solid color-mix(in srgb,var(--noc-accent) 25%,transparent)}.management-preview{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.management-message{min-height:1em;margin-top:6px;color:var(--noc-text-secondary);font-size:.7rem}.management-message.error{color:var(--noc-critical)}.password-state{margin-top:8px;color:var(--noc-text-secondary);font-size:.76rem}.detail-navigation{display:flex;gap:10px;justify-content:flex-end;align-items:center}.value-healthy,.operation-completed{color:var(--noc-healthy)!important}.value-warning,.operation-running{color:var(--noc-warning)!important}.value-critical,.operation-failed{color:var(--noc-critical)!important}.value-info{color:var(--noc-accent)!important}.value-unknown{color:var(--noc-unknown)!important}
.empty{padding:18px;text-align:center}
.empty a{color:var(--noc-accent)}
.shell[data-layout="compact"] .repeater{padding-block:4px}
.shell[data-layout="compact"] .row{margin-top:1px}
.shell[data-layout="constrained"]{padding:6px 8px}
.shell[data-layout="constrained"] .mission{align-items:flex-start}
.shell[data-layout="constrained"] .kpis{grid-template-columns:repeat(4,minmax(0,1fr))}
.shell[data-layout="constrained"] .metric{height:62px}
@container(max-width:800px){.noc-header{grid-template-columns:1fr}.header-controls{justify-content:flex-start}.header-progress{text-align:left}.ops-layout{grid-template-columns:1fr}.fleet-rows{grid-template-columns:repeat(2,minmax(0,1fr))}.detail-grid{grid-template-columns:1fr}.detail-panel.wide{grid-column:auto}}
@container(max-width:700px){.mission{display:block}.network-state{display:inline-flex;margin-top:6px}.meta{flex-wrap:wrap;white-space:normal}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.alerts{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.clock-panel{grid-template-columns:repeat(2,minmax(0,1fr))}.clock-actions{justify-content:flex-start}.clock-detail-grid{grid-template-columns:1fr}.fleet-rows{grid-template-columns:1fr}.detail-header{grid-template-columns:1fr}.detail-metrics,.management-preview{grid-template-columns:repeat(2,minmax(0,1fr))}.management-form{grid-template-columns:1fr}.detail-navigation{justify-content:flex-start}}
@media(prefers-reduced-motion:reduce){.battery-fill{transition:none}}
</style><section class="shell"></section>`;
        this.shadowRoot
          .querySelector(".shell")
          ?.addEventListener("click", (event) => {
            if (event.target?.closest?.("[data-management-action]"))
              this._handleManagementAction(event);
            else this._handleAction(event);
          });
        this.shadowRoot
          .querySelector(".shell")
          ?.addEventListener("input", (event) => this._captureManagementDraft(event));
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
    _serviceButton(label, domain, service, data, options = {}) {
      const key = `${domain}.${service}:${JSON.stringify(data || {})}`;
      const pending = this._pendingActions?.has(key);
      const button = this._element(
        "button",
        `clock-action${options.primary ? " primary" : ""}`,
        pending ? options.pendingLabel || "Working…" : label,
      );
      button.type = "button";
      button.disabled = Boolean(options.disabled || pending);
      button.dataset.actionKey = key;
      button.dataset.serviceDomain = domain;
      button.dataset.service = service;
      button.dataset.serviceData = JSON.stringify(data || {});
      button.dataset.actionKind = options.kind || "service";
      if (options.targetName) button.dataset.targetName = options.targetName;
      return button;
    }
    _managementFor(stableId) {
      const saved = this._managementSettings.get(stableId);
      if (!saved) {
        this._loadManagement(stableId);
        return { ...MANAGEMENT_DEFAULTS };
      }
      return { ...MANAGEMENT_DEFAULTS, ...saved };
    }
    _draftFor(stableId) {
      if (!this._managementDrafts.has(stableId))
        this._managementDrafts.set(stableId, {
          ...this._managementFor(stableId),
        });
      return this._managementDrafts.get(stableId);
    }
    async _loadManagement(stableId) {
      if (
        this._managementLoads.has(stableId) ||
        this._managementSettings.has(stableId) ||
        !this._hass?.callWS
      )
        return;
      this._managementLoads.add(stableId);
      try {
        const settings = await this._hass.callWS({
          type: "meshcore_noc/management/get",
          stable_id: stableId,
        });
        this._managementSettings.set(stableId, {
          ...MANAGEMENT_DEFAULTS,
          ...settings,
        });
        if (!this._managementDrafts.has(stableId))
          this._managementDrafts.set(stableId, {
            ...MANAGEMENT_DEFAULTS,
            ...settings,
          });
      } catch (error) {
        this._managementSettings.set(stableId, { ...MANAGEMENT_DEFAULTS });
        this._managementMessages.set(stableId, {
          text: `Settings unavailable: ${error?.message || "request rejected"}`,
          error: true,
        });
      } finally {
        this._managementLoads.delete(stableId);
        this._render("management-loaded");
      }
    }
    _captureManagementDraft(event) {
      const input = event.target?.closest?.("[data-management-field]");
      if (!input) return;
      const draft = this._draftFor(input.dataset.stableId);
      draft[input.dataset.managementField] = input.value;
      if (
        ["voltage_offset", "empty_voltage", "full_voltage"].includes(
          input.dataset.managementField,
        )
      )
        this._updateCalibrationPreview(input.dataset.stableId);
    }
    _updateCalibrationPreview(stableId) {
      const draft = this._draftFor(stableId);
      const raw = Number(
        this.shadowRoot?.querySelector(
          `[data-preview-raw="${stableId}"]`,
        )?.dataset.rawVoltage,
      );
      const offset = Number(draft.voltage_offset);
      const empty = Number(draft.empty_voltage);
      const full = Number(draft.full_voltage);
      const calibrated = raw + offset;
      const battery =
        Number.isFinite(calibrated) && full > empty
          ? Math.round(
              Math.max(0, Math.min(100, ((calibrated - empty) / (full - empty)) * 100)),
            )
          : null;
      const calibratedNode = this.shadowRoot?.querySelector(
        `[data-preview-calibrated="${stableId}"]`,
      );
      const offsetNode = this.shadowRoot?.querySelector(
        `[data-preview-offset="${stableId}"]`,
      );
      const batteryNode = this.shadowRoot?.querySelector(
        `[data-preview-battery="${stableId}"]`,
      );
      if (calibratedNode)
        calibratedNode.textContent = Number.isFinite(calibrated)
          ? `${calibrated.toFixed(3)} V`
          : "—";
      if (offsetNode)
        offsetNode.textContent = Number.isFinite(offset)
          ? `${offset.toFixed(3)} V`
          : "—";
      if (batteryNode)
        batteryNode.textContent = battery === null ? "—" : `${battery}%`;
    }
    async _handleManagementAction(event) {
      const button = event.target?.closest?.("[data-management-action]");
      if (!button || button.disabled) return;
      const stableId = button.dataset.stableId;
      const action = button.dataset.managementAction;
      const section = button.dataset.section;
      const saved = this._managementFor(stableId);
      const draft = this._draftFor(stableId);
      const sectionKeys = this._managementSectionKeys(section);
      if (action === "cancel") {
        for (const key of sectionKeys) draft[key] = saved[key];
        this._managementMessages.delete(stableId);
        this._render("management-cancelled");
        return;
      }
      if (action === "reset") {
        for (const key of sectionKeys) draft[key] = MANAGEMENT_DEFAULTS[key];
        this._managementMessages.set(stableId, {
          text: "Defaults loaded. Select Save to persist them.",
          error: false,
        });
        this._render("management-defaults-loaded");
        return;
      }
      button.disabled = true;
      try {
        if (!this._hass?.callWS)
          throw new Error("Home Assistant management API unavailable");
        if (action === "password-save") {
          const passwordInput = Array.from(
            this.shadowRoot?.querySelectorAll("[data-password-input]") || [],
          ).find((item) => item.dataset.stableId === stableId);
          const result = await this._hass.callWS({
            type: "meshcore_noc/management/set_password",
            stable_id: stableId,
            password: passwordInput?.value || "",
          });
          if (passwordInput) passwordInput.value = "";
          this._managementSettings.set(stableId, {
            ...saved,
            ...result,
          });
        } else if (action === "password-remove") {
          const result = await this._hass.callWS({
            type: "meshcore_noc/management/remove_password",
            stable_id: stableId,
          });
          this._managementSettings.set(stableId, {
            ...saved,
            ...result,
          });
        } else {
          const sectionSettings = { ...saved };
          for (const key of sectionKeys) sectionSettings[key] = draft[key];
          const settings = await this._hass.callWS({
            type: "meshcore_noc/management/save",
            stable_id: stableId,
            settings: sectionSettings,
          });
          this._managementSettings.set(stableId, {
            ...MANAGEMENT_DEFAULTS,
            ...settings,
          });
          this._managementDrafts.set(stableId, {
            ...MANAGEMENT_DEFAULTS,
            ...settings,
          });
        }
        this._managementMessages.set(stableId, {
          text:
            action === "password-remove"
              ? "Repeater password removed."
              : action === "password-save"
                ? "New repeater password saved."
                : "Repeater settings saved.",
          error: false,
        });
      } catch (error) {
        this._managementMessages.set(stableId, {
          text: error?.message || "Settings were not saved",
          error: true,
        });
      } finally {
        button.disabled = false;
        this._render("management-action-completed");
      }
    }
    _managementSectionKeys(section) {
      return (
        {
          calibration: ["voltage_offset", "empty_voltage", "full_voltage"],
          thresholds: [
            "battery_warning",
            "battery_critical",
            "fresh_max_age",
            "aging_max_age",
            "stale_max_age",
            "offline_max_age",
            "clock_warning",
            "clock_critical",
          ],
          identity: ["display_name"],
        }[section] || []
      );
    }
    _managementInput(
      form,
      stableId,
      field,
      label,
      value,
      options = {},
    ) {
      const wrapper = this._element("label", "", label);
      const input = this._element("input");
      input.type = options.type || "number";
      input.value = value ?? "";
      input.dataset.managementField = field;
      input.dataset.stableId = stableId;
      if (options.step) input.step = String(options.step);
      if (options.min !== undefined) input.min = String(options.min);
      if (options.max !== undefined) input.max = String(options.max);
      if (options.placeholder) input.placeholder = options.placeholder;
      wrapper.append(input);
      form.append(wrapper);
      return input;
    }
    _managementButtons(panel, stableId, section) {
      const actions = this._element("div", "detail-actions");
      for (const [label, action, primary] of [
        ["Save", "save", true],
        ["Cancel", "cancel", false],
        ["Reset Defaults", "reset", false],
      ]) {
        const button = this._element(
          "button",
          `clock-action${primary ? " primary" : ""}`,
          label,
        );
        button.type = "button";
        button.dataset.managementAction = action;
        button.dataset.stableId = stableId;
        button.dataset.section = section;
        actions.append(button);
      }
      panel.append(actions);
    }
    _managementMessage(panel, stableId) {
      const message = this._managementMessages.get(stableId);
      panel.append(
        this._element(
          "div",
          `management-message${message?.error ? " error" : ""}`,
          message?.text || "",
        ),
      );
    }
    _displayName(repeater) {
      const configured = this._managementFor(repeater.stableId).display_name;
      return shortDisplayName(configured || repeater.name, repeater.stableId);
    }
    async _handleAction(event) {
      const button = event.target?.closest?.(
        "[data-entity-id],[data-service]",
      );
      if (!button || button.disabled) return;
      const entityId = button.dataset.entityId;
      const actionKey = button.dataset.actionKey || entityId;
      const kind = button.dataset.actionKind;
      const targetName = button.dataset.targetName;
      this._pendingActions = this._pendingActions || new Set();
      this._pendingActions.add(actionKey);
      const requestedMessage = actionRequestMessage(kind, targetName);
      this._showFeedback(requestedMessage);
      this._render("clock-action-requested");
      try {
        if (!this._hass?.callService)
          throw new Error("Home Assistant action service unavailable");
        if (button.dataset.service) {
          await this._hass.callService(
            button.dataset.serviceDomain,
            button.dataset.service,
            JSON.parse(button.dataset.serviceData || "{}"),
          );
        } else {
          await this._hass.callService("button", "press", {
            entity_id: entityId,
          });
        }
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
        this._pendingActions.delete(actionKey);
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
    _historyChart(title, repeaters) {
      const chart = this._element("meshcore-noc-history-chart");
      chart.dataset.chartConfig = JSON.stringify({
        title,
        hours: 24,
        series: repeaters
          .filter((repeater) => repeater.entities.voltage)
          .map((repeater) => ({
            entity: repeater.entities.voltage,
            name: shortDisplayName(repeater.name, repeater.stableId),
          })),
      });
      return chart;
    }
    _combinedHeader(fleet, repeaters, metrics, check, sync) {
      const baseState = overallState(metrics.health);
      const controls = fleetControlState(check, sync);
      const alerts = networkAlerts(this._hass, metrics);
      const state = alerts.some((alert) => alert.severity === "critical")
        ? "critical"
        : alerts.length && baseState === "healthy"
          ? "warning"
          : baseState;
      const header = this._element("header", "noc-header");
      const summary = this._element("div");
      const heading = this._element("div", "noc-heading");
      heading.append(
        this._icon("mdi:access-point-network"),
        this._element("h1", "", "MeshCore NOC"),
      );
      const statusLine = this._element("div", "status-line");
      statusLine.append(
        this._element("span", `status-dot ${state}`),
        this._element("b", state, state),
        document.createTextNode(
          `· ${metrics.online}/${metrics.managed} Online · ${
            alerts.length
              ? `${alerts.length} active issue${alerts.length === 1 ? "" : "s"}`
              : "No active alerts"
          }`,
        ),
      );
      const clockLine = this._element(
        "div",
        "clock-line",
        `Fleet sync ${formatDateTime(
          stateValue(this._hass, fleet.lastSync)?.state,
        )} · Auto ${sync.automaticEnabled ? "on" : "off"} · Clock ${
          clockSummaryTile(check.health).value
        }`,
      );
      summary.append(heading, statusLine, clockLine);
      const actions = this._element("div", "header-controls");
      actions.append(
        this._actionButton("Check All", fleet.checkAll, {
          disabled: controls.checkAllDisabled,
          kind: "fleet",
          pendingLabel: "Checking…",
        }),
        this._actionButton("Sync All", fleet.syncAll, {
          disabled: controls.syncAllDisabled,
          kind: "fleet-sync",
          pendingLabel: "Synchronising…",
          primary: true,
        }),
      );
      if (check.active)
        actions.append(
          this._actionButton("Cancel", fleet.cancel, {
            disabled: controls.cancelDisabled,
            kind: "cancel",
            pendingLabel: "Cancelling…",
          }),
        );
      const operation = sync.active
        ? `${sync.completed} of ${sync.total} complete · ${sync.currentRepeater}`
        : check.active
          ? `${check.completed} of ${check.total} complete · ${check.currentRepeater}`
          : sync.result !== "—"
            ? `Last sync ${String(sync.result).replaceAll("_", " ")} · ${sync.successful} successful · ${sync.failed} failed`
            : "No clock operation running";
      actions.append(
        this._element(
          "div",
          `header-progress ${operationClass(operation)}`,
          operation,
        ),
      );
      const alertRow = this._element("div", "header-alerts");
      if (!alerts.length) {
        alertRow.append(
          this._element("span", "alert-chip healthy", "✓ No active alerts"),
        );
      } else {
        for (const alert of alerts.slice(0, 6)) {
          const link = this._element(
            "a",
            `alert-chip ${alert.severity}`,
          );
          link.href = alert.target;
          link.append(this._icon(alert.icon), document.createTextNode(alert.text));
          alertRow.append(link);
        }
        if (alerts.length > 6)
          alertRow.append(
            this._element(
              "span",
              "alert-chip warning",
              `+${alerts.length - 6} more`,
            ),
          );
      }
      const warning = this._element(
        "div",
        "source-warning",
        "Repeaters are synchronised to the connected MeshCore companion clock. Ensure the companion clock is correct before enabling automatic synchronisation.",
      );
      header.append(summary, actions, alertRow, warning);
      return header;
    }
    _fleetList(repeaters, metrics) {
      const panel = this._element("section", "fleet-list");
      panel.append(
        this._element("h2", "", `Fleet · ${repeaters.length} managed`),
      );
      const rows = this._element("div", "fleet-rows");
      for (const repeater of repeaters) {
        this._loadManagement(repeater.stableId);
        const status =
          metrics.statuses.find(
            (item) => item.repeater.stableId === repeater.stableId,
          ) || repeaterStatus(this._hass, repeater);
        const voltage = numericState(this._hass, repeater.entities.voltage);
        const battery = clampBattery(
          numericState(this._hass, repeater.entities.battery),
        );
        const clockState = stateValue(
          this._hass,
          repeater.entities.clockStatus,
        );
        const clock = clockStatusPresentation(clockState?.state);
        const clockOffset = signedClockOffset(
          this._hass,
          repeater.entities.clockOffset,
        );
        const row = this._element("a", `fleet-row ${status.label}`);
        row.href = `/meshcore-noc/${safePath(repeater.stableId)}`;
        row.setAttribute(
          "aria-label",
          `Open ${this._displayName(repeater)} details`,
        );
        row.append(
          this._element("span", `status-dot ${status.label}`),
          this._element(
            "span",
            "fleet-name",
            this._displayName(repeater),
          ),
          this._element(
            "span",
            `fleet-value ${status.label}`,
            status.label === "offline"
              ? "Offline"
              : voltage === null
                ? "No data"
                : `${voltage.toFixed(2)} V`,
          ),
          this._element(
            "span",
            `fleet-value ${
              battery === null
                ? "unknown"
                : battery < this._managementFor(repeater.stableId).battery_critical
                  ? "critical"
                  : battery < this._managementFor(repeater.stableId).battery_warning
                    ? "warning"
                    : "healthy"
            }`,
            battery === null ? "—" : `${Math.round(battery)}%`,
          ),
          this._element(
            "span",
            `fleet-state ${clock.className}`,
            `Last Seen ${formatAge(
              repeaterAgeSeconds(this._hass, repeater),
            )} · Clock ${clockOffset}`,
          ),
        );
        rows.append(row);
      }
      panel.append(rows);
      return panel;
    }
    _detailMetric(container, label, value, valueClass = "") {
      const metric = this._element("div", "detail-metric", label);
      metric.append(this._element("b", valueClass, value));
      container.append(metric);
    }
    _detailView(repeater, repeaters, fleet, check, sync) {
      this._loadManagement(repeater.stableId);
      const settings = this._managementFor(repeater.stableId);
      const draft = this._draftFor(repeater.stableId);
      const status = repeaterStatus(this._hass, repeater);
      const voltageState = stateValue(this._hass, repeater.entities.voltage);
      const batteryState = stateValue(this._hass, repeater.entities.battery);
      const healthState = stateValue(this._hass, repeater.entities.health);
      const freshnessState = stateValue(this._hass, repeater.entities.freshness);
      const clockState = stateValue(this._hass, repeater.entities.clockStatus);
      const clock = clockStatusPresentation(clockState?.state);
      const clockAttributes = clockState?.attributes || {};
      const voltageAttributes = voltageState?.attributes || {};
      const batteryAttributes = batteryState?.attributes || {};
      const name = this._displayName(repeater);
      const online =
        status.label !== "offline" &&
        (numericState(this._hass, repeater.entities.voltage) !== null ||
          numericState(this._hass, repeater.entities.battery) !== null);
      const fragment = document.createDocumentFragment();
      const header = this._element("header", `detail-header ${status.label}`);
      const title = this._element("div");
      title.append(
        this._element("h1", "", name),
        this._element(
          "div",
          "detail-summary",
          `${status.label} · ${
            online ? "Online" : status.label === "offline" ? "Offline" : "Unknown"
          } · ${this._value(repeater.entities.voltage)} · ${this._value(
            repeater.entities.battery,
          )} · Last Seen ${formatAge(
            repeaterAgeSeconds(this._hass, repeater),
          )} · Clock ${clock.label}`,
        ),
      );
      const navigation = this._element("nav", "detail-navigation");
      const index = repeaters.findIndex(
        (item) => item.stableId === repeater.stableId,
      );
      const previous = repeaters[(index - 1 + repeaters.length) % repeaters.length];
      const next = repeaters[(index + 1) % repeaters.length];
      const previousLink = this._element("a", "back-link", "← Previous Repeater");
      previousLink.href = `/meshcore-noc/${safePath(previous.stableId)}`;
      const back = this._element("a", "back-link", "Fleet");
      back.href = "/meshcore-noc/network";
      const nextLink = this._element("a", "back-link", "Next Repeater →");
      nextLink.href = `/meshcore-noc/${safePath(next.stableId)}`;
      navigation.append(previousLink, back, nextLink);
      header.append(title, navigation);
      fragment.append(header, this._historyChart(`${name} voltage`, [repeater]));
      const grid = this._element("section", "detail-grid");
      const monitoring = this._element("section", "detail-panel");
      monitoring.append(this._element("h2", "", "Monitoring"));
      const monitoringMetrics = this._element("div", "detail-metrics");
      this._detailMetric(
        monitoringMetrics,
        "Calibrated voltage",
        this._value(repeater.entities.voltage),
      );
      this._detailMetric(
        monitoringMetrics,
        "Battery",
        this._value(repeater.entities.battery),
      );
      this._detailMetric(
        monitoringMetrics,
        "Health",
        healthState?.state || "Unknown",
      );
      this._detailMetric(
        monitoringMetrics,
        "Last Seen status",
        freshnessState?.attributes?.freshness_status || "Unknown",
      );
      this._detailMetric(
        monitoringMetrics,
        "Last heard",
        formatAge(repeaterAgeSeconds(this._hass, repeater)),
      );
      this._detailMetric(
        monitoringMetrics,
        "Clock",
        `${clock.label} · ${signedClockOffset(
          this._hass,
          repeater.entities.clockOffset,
        )}`,
      );
      monitoring.append(monitoringMetrics);
      const clockPanel = this._element("section", `detail-panel ${clock.className}`);
      clockPanel.append(this._element("h2", "", "Repeater clock"));
      const clockMetrics = this._element("div", "detail-metrics");
      const clockRows = [
        ["Offset", signedClockOffset(this._hass, repeater.entities.clockOffset)],
        ["Last checked", formatDateTime(clockAttributes.last_clock_attempt)],
        ["Last synchronised", formatDateTime(clockAttributes.last_sync_time)],
        ["Operation", clockAttributes.sync_running ? "Synchronising" : clockAttributes.request_state || "Idle"],
        ["Last response", clockAttributes.last_sync_response || clockAttributes.response_text || "—"],
        ["Last error", clockAttributes.last_sync_error || clockAttributes.last_clock_attempt_error || "—"],
      ];
      for (const [label, value] of clockRows)
        this._detailMetric(
          clockMetrics,
          label,
          value,
          label === "Operation" ? operationClass(value) : "",
        );
      const busy = repeaterClockBusy(this._hass, repeater, check, sync);
      const clockActions = this._element("div", "detail-actions");
      clockActions.append(
        this._actionButton("Check this repeater", repeater.entities.checkClock, {
          disabled: busy,
          kind: "repeater",
          targetName: name,
          pendingLabel: "Checking…",
        }),
        this._serviceButton(
          "Sync this repeater",
          DOMAIN,
          "sync_repeater_clock",
          { repeater_id: repeater.stableId },
          {
            disabled: busy || !repeater.entities.clockStatus,
            kind: "repeater-sync",
            targetName: name,
            pendingLabel: "Synchronising…",
            primary: true,
          },
        ),
      );
      clockPanel.append(clockMetrics, clockActions);
      const identity = this._element("section", "detail-panel");
      identity.append(this._element("h2", "", "Identity and display"));
      const identityMetrics = this._element("div", "detail-metrics");
      const sourceEntity = voltageAttributes.source_entity;
      const sourceState = stateValue(this._hass, sourceEntity);
      const identityRows = [
        ["Full source name", sourceState?.attributes?.friendly_name || repeater.name],
        ["Stable identifier", repeater.stableId],
        ["Public-key prefix", clockAttributes.pubkey_prefix || "Unavailable"],
        ["Dashboard visibility", "Managed by NOC selection"],
        ["Display order", "Alphabetical"],
      ];
      for (const [label, value] of identityRows)
        this._detailMetric(identityMetrics, label, value);
      const identityForm = this._element("div", "management-form");
      this._managementInput(
        identityForm,
        repeater.stableId,
        "display_name",
        "Dashboard Display Name",
        draft.display_name || "",
        {
          type: "text",
          placeholder: shortDisplayName(repeater.name, repeater.stableId),
        },
      );
      const deviceLink = this._element(
        "a",
        "back-link",
        "Open Home Assistant device settings",
      );
      deviceLink.href = `/config/devices/device/${repeater.deviceId}`;
      identity.append(identityMetrics, identityForm);
      this._managementButtons(identity, repeater.stableId, "identity");
      identity.append(deviceLink);
      const calibration = this._element("section", "detail-panel");
      calibration.append(this._element("h2", "", "Battery calibration"));
      const calibrationForm = this._element("div", "management-form");
      this._managementInput(
        calibrationForm,
        repeater.stableId,
        "voltage_offset",
        "Voltage Offset (V)",
        draft.voltage_offset,
        { step: 0.001, min: -2, max: 2 },
      );
      this._managementInput(
        calibrationForm,
        repeater.stableId,
        "empty_voltage",
        "Empty Voltage (V)",
        draft.empty_voltage,
        { step: 0.001, min: 2, max: 6 },
      );
      this._managementInput(
        calibrationForm,
        repeater.stableId,
        "full_voltage",
        "Full Voltage (V)",
        draft.full_voltage,
        { step: 0.001, min: 2, max: 6 },
      );
      const rawVoltage =
        voltageAttributes.raw_voltage === null ||
        voltageAttributes.raw_voltage === undefined
          ? Number.NaN
          : Number(voltageAttributes.raw_voltage);
      const previewVoltage = rawVoltage + Number(draft.voltage_offset);
      const previewBattery =
        Number.isFinite(previewVoltage) &&
        Number(draft.full_voltage) > Number(draft.empty_voltage)
          ? Math.round(
              Math.max(
                0,
                Math.min(
                  100,
                  ((previewVoltage - Number(draft.empty_voltage)) /
                    (Number(draft.full_voltage) - Number(draft.empty_voltage))) *
                    100,
                ),
              ),
            )
          : null;
      const preview = this._element("div", "management-preview");
      const rawPreview = this._element("div", "detail-metric", "Raw Voltage");
      rawPreview.dataset.previewRaw = repeater.stableId;
      rawPreview.dataset.rawVoltage = Number.isFinite(rawVoltage)
        ? String(rawVoltage)
        : "";
      rawPreview.append(
        this._element(
          "b",
          "",
          Number.isFinite(rawVoltage) ? `${rawVoltage.toFixed(3)} V` : "—",
        ),
      );
      const offsetPreview = this._element("div", "detail-metric", "Offset");
      const offsetValue = this._element("b", "", `${draft.voltage_offset} V`);
      offsetValue.dataset.previewOffset = repeater.stableId;
      offsetPreview.append(offsetValue);
      const calibratedPreview = this._element(
        "div",
        "detail-metric",
        "Calibrated Voltage",
      );
      const calibratedValue = this._element(
        "b",
        "",
        Number.isFinite(previewVoltage)
          ? `${previewVoltage.toFixed(3)} V`
          : "—",
      );
      calibratedValue.dataset.previewCalibrated = repeater.stableId;
      calibratedPreview.append(calibratedValue);
      const batteryPreview = this._element(
        "div",
        "detail-metric",
        "Calculated Battery %",
      );
      const batteryValue = this._element(
        "b",
        "",
        previewBattery === null ? "—" : `${previewBattery}%`,
      );
      batteryValue.dataset.previewBattery = repeater.stableId;
      batteryPreview.append(batteryValue);
      preview.append(
        rawPreview,
        offsetPreview,
        calibratedPreview,
        batteryPreview,
      );
      calibrationForm.append(preview);
      calibration.append(calibrationForm);
      this._managementButtons(calibration, repeater.stableId, "calibration");
      const thresholds = this._element("section", "detail-panel wide");
      thresholds.append(this._element("h2", "", "Monitoring thresholds"));
      const thresholdForm = this._element("div", "management-form");
      const thresholdFields = [
        ["battery_warning", "Battery Warning (%)", 1, 1, 100],
        ["battery_critical", "Battery Critical (%)", 1, 0, 99],
        ["fresh_max_age", "Fresh maximum age (seconds)", 1, 60, 604800],
        ["aging_max_age", "Aging maximum age (seconds)", 1, 60, 604800],
        ["stale_max_age", "Stale maximum age (seconds)", 1, 60, 604800],
        ["offline_max_age", "Offline at age (seconds)", 1, 60, 604800],
        ["clock_warning", "Clock Warning (seconds)", 1, 1, 86400],
        ["clock_critical", "Clock Critical (seconds)", 1, 1, 86400],
      ];
      for (const [field, label, step, min, max] of thresholdFields)
        this._managementInput(
          thresholdForm,
          repeater.stableId,
          field,
          label,
          draft[field],
          { step, min, max },
        );
      thresholds.append(thresholdForm);
      this._managementButtons(thresholds, repeater.stableId, "thresholds");
      const access = this._element("section", "detail-panel wide");
      access.append(this._element("h2", "", "Repeater access"));
      access.append(
        this._element(
          "div",
          `password-state ${settings.password_configured ? "healthy" : "unknown"}`,
          `Status: ${settings.password_configured ? "Configured ✓" : "Not configured"}`,
        ),
      );
      access.append(
        this._element(
          "div",
          "password-state",
          `Last changed: ${
            settings.password_last_changed
              ? formatDateTime(settings.password_last_changed)
              : "Never"
          }`,
        ),
      );
      const passwordForm = this._element("div", "management-form");
      const passwordLabel = this._element(
        "label",
        "",
        settings.password_configured ? "Change password" : "New password",
      );
      const passwordInput = this._element("input");
      passwordInput.type = "password";
      passwordInput.autocomplete = "new-password";
      passwordInput.dataset.passwordInput = "true";
      passwordInput.dataset.stableId = repeater.stableId;
      passwordInput.placeholder = "Enter a new password";
      passwordLabel.append(passwordInput);
      passwordForm.append(passwordLabel);
      access.append(passwordForm);
      const passwordActions = this._element("div", "detail-actions");
      for (const [label, action, primary, disabled] of [
        ["Save password", "password-save", true, false],
        [
          "Remove password",
          "password-remove",
          false,
          !settings.password_configured,
        ],
      ]) {
        const button = this._element(
          "button",
          `clock-action${primary ? " primary" : ""}`,
          label,
        );
        button.type = "button";
        button.disabled = disabled;
        button.dataset.managementAction = action;
        button.dataset.stableId = repeater.stableId;
        passwordActions.append(button);
      }
      access.append(passwordActions);
      this._managementMessage(access, repeater.stableId);
      const advanced = this._element("details", "detail-panel wide advanced");
      advanced.append(this._element("summary", "", "Advanced diagnostics"));
      const diagnosticMetrics = this._element("div", "detail-metrics");
      const diagnosticRows = [
        ["Source entity", sourceEntity || "Unavailable"],
        ["Raw source value", sourceState?.state || "Unavailable"],
        ["Last source update", formatDateTime(voltageAttributes.last_source_update)],
        ["Integration health", healthState?.state || "Unknown"],
        ["Clock request state", clockAttributes.request_state || "Idle"],
        ["Clock error", clockAttributes.last_error || clockAttributes.last_sync_error || "—"],
      ];
      for (const [label, value] of diagnosticRows)
        this._detailMetric(diagnosticMetrics, label, value);
      advanced.append(diagnosticMetrics);
      grid.append(
        monitoring,
        clockPanel,
        identity,
        calibration,
        thresholds,
        access,
        advanced,
      );
      fragment.append(grid);
      return fragment;
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
        cell.append(
          this._element(
            "b",
            ["Clock State", "Fleet Sync State"].includes(label)
              ? operationClass(value)
              : "",
            value,
          ),
        );
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
        "Last Seen",
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
      const syncFleetMetrics = fleetSyncMetrics(this._hass, fleetClock);
      if (this._config.section === "detail") {
        const repeater = repeaters.find(
          (item) => item.stableId === this._config.stable_id,
        );
        if (repeater)
          renderShell.append(
            this._detailView(
              repeater,
              repeaters,
              fleetClock,
              clockFleetMetrics,
              syncFleetMetrics,
            ),
          );
        else
          renderShell.append(
            this._element(
              "div",
              "empty",
              "This managed repeater is no longer available.",
            ),
          );
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
      renderShell.append(
        this._combinedHeader(
          fleetClock,
          repeaters,
          metrics,
          clockFleetMetrics,
          syncFleetMetrics,
        ),
      );
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
        renderShell.append(empty);
      } else {
        const operations = this._element("section", "ops-layout");
        operations.append(
          this._fleetList(repeaters, metrics),
          this._historyChart("Fleet calibrated voltage", repeaters),
        );
        renderShell.append(operations);
      }
      if (this._actionMessage)
        renderShell.append(
          this._element(
            "div",
            `action-feedback${this._actionMessageError ? " error" : ""}`,
            this._actionMessage,
          ),
        );
      this._finishRender(
        scrollSnapshot,
        shell,
        renderShell,
        structureKey,
        structuralChange,
        reason,
      );
      return;
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
      for (const chart of shell.querySelectorAll("meshcore-noc-history-chart")) {
        try {
          chart.setConfig(JSON.parse(chart.dataset.chartConfig || "{}"));
          chart.hass = this._hass;
        } catch (_error) {
          chart.setConfig({ title: "Voltage history", series: [] });
        }
      }
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
    if (!registry.get("meshcore-noc-history-chart"))
      registry.define("meshcore-noc-history-chart", MeshCoreNocHistoryChart);
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
      networkAlerts,
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
      shortDisplayName,
      scrollContainerFor,
      scrollSnapshotForRender,
      signedClockOffset,
      readableClockOffset,
    };
})();
