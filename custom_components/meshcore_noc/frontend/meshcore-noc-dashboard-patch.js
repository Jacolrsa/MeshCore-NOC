/* MeshCore NOC beta15 clock/password and fleet severity UX patch. */
(() => {
  "use strict";

  const PATCH_MARKER = "__meshcoreNocClockSyncUxPatchBeta15";
  if (globalThis[PATCH_MARKER]) return;
  globalThis[PATCH_MARKER] = true;

  const describeError = (error) => {
    const candidates = [error?.message, error?.error, error?.code, typeof error === "string" ? error : null].filter(Boolean);
    const message = String(candidates[0] || "").trim();
    if (!message || message.toLowerCase() === "unknown error" || message === "[object Object]")
      return "Home Assistant rejected the password request. Check Settings → System → Logs for the detailed error.";
    return message;
  };

  const findPanel = (fragment, heading) =>
    Array.from(fragment.querySelectorAll?.("section.detail-panel") || []).find(
      (panel) => panel.querySelector("h2")?.textContent?.trim() === heading,
    ) || null;

  const metricByLabel = (panel, label) =>
    Array.from(panel?.querySelectorAll?.(".detail-metric") || []).find((metric) => {
      const firstText = Array.from(metric.childNodes || []).find(
        (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue?.trim(),
      );
      return firstText?.nodeValue?.trim() === label;
    }) || null;

  const severityRank = Object.freeze({ unknown: 0, healthy: 1, warning: 2, degraded: 3, critical: 4 });
  const worse = (left, right) =>
    (severityRank[right] ?? 0) > (severityRank[left] ?? 0) ? right : left;

  const statusSeverity = (row) => {
    const classes = row?.classList;
    if (!classes) return "unknown";
    if (classes.contains("offline") || classes.contains("critical") || classes.contains("unhealthy")) return "critical";
    if (classes.contains("degraded") || classes.contains("stale")) return "degraded";
    if (classes.contains("warning") || classes.contains("aging")) return "warning";
    if (classes.contains("healthy") || classes.contains("fresh")) return "healthy";
    return "unknown";
  };

  const clockSeverity = (state) => {
    const value = String(state || "").toLowerCase();
    if (value === "critical") return "critical";
    if (value === "drift") return "degraded";
    if (value === "minor drift") return "warning";
    if (value === "in sync") return "healthy";
    return "unknown";
  };

  const install = async () => {
    if (typeof customElements === "undefined") return;
    await customElements.whenDefined("meshcore-noc-overview-card");
    const Card = customElements.get("meshcore-noc-overview-card");
    if (!Card || Card.prototype.__clockSyncUxPatchedBeta15) return;
    Card.prototype.__clockSyncUxPatchedBeta15 = true;

    const originalDetailView = Card.prototype._detailView;
    const originalHandleAction = Card.prototype._handleAction;
    const originalManagementAction = Card.prototype._handleManagementAction;
    const originalCombinedHeader = Card.prototype._combinedHeader;
    const originalFleetList = Card.prototype._fleetList;

    Card.prototype._ensureClockSyncPatchStyle = function () {
      if (!this.shadowRoot || this.shadowRoot.querySelector("style[data-clock-sync-patch]")) return;
      const style = document.createElement("style");
      style.dataset.clockSyncPatch = "true";
      style.textContent = `
.sync-access-state{margin-top:8px;padding:7px 9px;border:1px solid var(--noc-border);border-radius:8px;background:var(--noc-panel-alt);font-size:.72rem;font-weight:700}
.sync-access-state.warning{border-left:4px solid var(--noc-warning);color:var(--noc-warning)}
.sync-access-state.healthy{border-left:4px solid var(--noc-healthy);color:var(--noc-healthy)}
.sync-live-log{margin-top:9px;padding:8px 9px;border:1px solid var(--noc-border);border-radius:8px;background:#0d1115;color:var(--noc-text-secondary);font:600 .69rem/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
.sync-live-log strong{display:block;margin-bottom:5px;color:var(--noc-text-primary);font-family:system-ui,sans-serif}
.sync-live-log .sync-line{white-space:pre-wrap;overflow-wrap:anywhere}
.sync-live-log.running{border-left:4px solid var(--noc-accent)}
.management-message.error{font-weight:700}
.fleet-row.fleet-severity-healthy{border-left-color:var(--noc-healthy)!important}
.fleet-row.fleet-severity-warning{border-left-color:var(--noc-warning)!important}
.fleet-row.fleet-severity-degraded{border-left-color:var(--noc-degraded)!important}
.fleet-row.fleet-severity-critical{border-left-color:var(--noc-critical)!important}
.fleet-row.fleet-severity-unknown{border-left-color:var(--noc-unknown)!important}
.fleet-row.fleet-severity-healthy .status-dot,.fleet-row.fleet-severity-healthy .fleet-name{color:var(--noc-healthy)!important}
.fleet-row.fleet-severity-warning .status-dot,.fleet-row.fleet-severity-warning .fleet-name{color:var(--noc-warning)!important}
.fleet-row.fleet-severity-degraded .status-dot,.fleet-row.fleet-severity-degraded .fleet-name{color:var(--noc-degraded)!important}
.fleet-row.fleet-severity-critical .status-dot,.fleet-row.fleet-severity-critical .fleet-name{color:var(--noc-critical)!important}
.fleet-row.fleet-severity-unknown .status-dot,.fleet-row.fleet-severity-unknown .fleet-name{color:var(--noc-unknown)!important}
.fleet-row .fleet-state.healthy{color:var(--noc-healthy)!important}
.fleet-row .fleet-state.warning{color:var(--noc-warning)!important}
.fleet-row .fleet-state.degraded{color:var(--noc-degraded)!important}
.fleet-row .fleet-state.critical{color:var(--noc-critical)!important}
.fleet-row .fleet-state.unknown{color:var(--noc-unknown)!important}
`;
      this.shadowRoot.prepend(style);
    };

    Card.prototype._combinedHeader = function (...args) {
      const header = originalCombinedHeader.call(this, ...args);
      const warning = header?.querySelector?.(".source-warning");
      if (warning)
        warning.textContent = "Repeater clock synchronisation uses Home Assistant UTC time as the authoritative source.";
      return header;
    };

    Card.prototype._fleetList = function (repeaters, metrics) {
      const panel = originalFleetList.call(this, repeaters, metrics);
      this._ensureClockSyncPatchStyle();
      const rows = Array.from(panel?.querySelectorAll?.(".fleet-row") || []);
      rows.forEach((row, index) => {
        const repeater = repeaters[index];
        if (!repeater) return;
        let severity = statusSeverity(row);
        const settings = this._managementFor(repeater.stableId) || {};
        const batteryState = this._hass?.states?.[repeater.entities?.battery];
        const battery = Number(batteryState?.state);
        if (Number.isFinite(battery)) {
          const critical = Number(settings.battery_critical ?? 20);
          const warning = Number(settings.battery_warning ?? 40);
          if (battery < critical) severity = worse(severity, "critical");
          else if (battery < warning) severity = worse(severity, "warning");
        }
        const clockState = this._hass?.states?.[repeater.entities?.clockStatus];
        severity = worse(severity, clockSeverity(clockState?.state));
        for (const name of Object.keys(severityRank)) row.classList.remove(`fleet-severity-${name}`);
        row.classList.add(`fleet-severity-${severity}`);
      });
      return panel;
    };

    Card.prototype._detailView = function (...args) {
      const fragment = originalDetailView.call(this, ...args);
      const repeater = args[0];
      const checkMetrics = args[3] || {};
      const syncMetrics = args[4] || {};
      if (!repeater) return fragment;
      this._ensureClockSyncPatchStyle();

      const clockPanel = findPanel(fragment, "Repeater clock");
      const accessPanel = findPanel(fragment, "Repeater access");
      if (clockPanel && accessPanel && clockPanel.parentNode === accessPanel.parentNode) clockPanel.after(accessPanel);

      const passwordInput = accessPanel?.querySelector?.("[data-password-input]");
      if (passwordInput) {
        passwordInput.type = "text";
        passwordInput.autocomplete = "off";
        passwordInput.placeholder = "Enter repeater administrator password";
      }

      if (!clockPanel) return fragment;
      const settings = this._managementFor(repeater.stableId);
      const clockState = this._hass?.states?.[repeater.entities.clockStatus];
      const attributes = clockState?.attributes || {};

      const startupQueued =
        String(attributes.request_state || "").toLowerCase() === "queued" &&
        !attributes.last_clock_attempt && !attributes.sync_running;
      if (startupQueued && !checkMetrics.active && !syncMetrics.active) {
        for (const button of clockPanel.querySelectorAll("button")) {
          const label = button.textContent?.trim();
          if (["Check this repeater", "Sync this repeater"].includes(label)) button.disabled = false;
        }
        const operation = metricByLabel(clockPanel, "Operation");
        const value = operation?.querySelector("b");
        if (value) { value.textContent = "Idle"; value.className = ""; }
      }

      const accessState = this._element(
        "div",
        `sync-access-state ${settings.password_configured ? "healthy" : "warning"}`,
        settings.password_configured
          ? "Repeater access ✓ Administrator password is saved for clock checks and synchronisation."
          : "Repeater access required: save the administrator password below before using clock check or synchronisation.",
      );
      clockPanel.append(accessState);

      const transcript = String(attributes.last_sync_response || "").trim();
      if (transcript) {
        const log = this._element("div", `sync-live-log${attributes.sync_running ? " running" : ""}`);
        log.append(this._element("strong", "", attributes.sync_running ? "Clock sync — working…" : "Last clock sync activity"));
        const lines = transcript.split("\n").filter(Boolean).slice(-20);
        for (const line of lines) log.append(this._element("div", "sync-line", line));
        clockPanel.append(log);
      }
      return fragment;
    };

    Card.prototype._handleAction = async function (event) {
      const button = event.target?.closest?.("[data-entity-id],[data-service]");
      if (button?.dataset?.actionKind === "repeater-sync") {
        let data = {};
        try { data = JSON.parse(button.dataset.serviceData || "{}"); } catch (_error) { data = {}; }
        const stableId = data.repeater_id;
        const settings = stableId ? this._managementFor(stableId) : null;
        if (stableId && !settings?.password_configured) {
          this._managementMessages = this._managementMessages || new Map();
          this._managementMessages.set(stableId, { text: "Password required. Enter and save the repeater administrator password before clock synchronisation.", error: true });
          this._showFeedback("Clock sync not started — repeater administrator password is required.", true);
          this._render("clock-sync-password-required");
          setTimeout(() => {
            const input = Array.from(this.shadowRoot?.querySelectorAll("[data-password-input]") || []).find((item) => item.dataset.stableId === stableId);
            input?.scrollIntoView?.({ behavior: "smooth", block: "center" });
            input?.focus?.();
          }, 0);
          return;
        }
      }
      return originalHandleAction.call(this, event);
    };

    Card.prototype._handleManagementAction = async function (event) {
      const button = event.target?.closest?.("[data-management-action]");
      if (!button || !["password-save", "password-remove"].includes(button.dataset.managementAction))
        return originalManagementAction.call(this, event);
      if (button.disabled) return;

      const stableId = button.dataset.stableId;
      const action = button.dataset.managementAction;
      const saved = this._managementFor(stableId);
      button.disabled = true;
      try {
        if (!this._hass?.callWS) throw new Error("Home Assistant management API unavailable");
        let result;
        if (action === "password-save") {
          const passwordInput = Array.from(this.shadowRoot?.querySelectorAll("[data-password-input]") || []).find((item) => item.dataset.stableId === stableId);
          const password = passwordInput?.value || "";
          if (!password) {
            this._managementMessages.set(stableId, { text: "Enter the repeater administrator password first.", error: true });
            this._render("password-empty");
            return;
          }
          result = await this._hass.callWS({ type: "meshcore_noc/management/set_password", stable_id: stableId, password });
          if (!result || result.password_configured !== true) throw new Error("Password save was not confirmed by MeshCore NOC.");
          if (passwordInput) passwordInput.value = "";
        } else {
          result = await this._hass.callWS({ type: "meshcore_noc/management/remove_password", stable_id: stableId });
        }

        this._managementSettings.set(stableId, { ...saved, ...result });
        this._managementMessages.set(stableId, {
          text: action === "password-save"
            ? "Password saved. It is used for authenticated clock checks and synchronisation."
            : "Repeater password removed. Clock checks and synchronisation will require a saved password.",
          error: false,
        });
      } catch (error) {
        this._managementMessages.set(stableId, { text: `Password action failed: ${describeError(error)}`, error: true });
      } finally {
        button.disabled = false;
        this._render("password-action-completed");
      }
    };

    console.info("MeshCore NOC beta15 clock/password/fleet severity UX patch loaded");
  };

  install().catch((error) => console.error("MeshCore NOC beta15 UX patch failed", error));
})();

/* MeshCore NOC 1.1 telemetry-chart stability and interaction patch. */
(() => {
  "use strict";

  const PATCH_MARKER = "__meshcoreNocTelemetryChartV11";
  if (globalThis[PATCH_MARKER]) return;
  globalThis[PATCH_MARKER] = true;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const COLORS = ["#4da3ff", "#36c96b", "#f6c344", "#ff8b3d", "#d77bff", "#4dd6c5", "#ff6f91", "#9cc45b"];
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const svgNode = (tag, attributes = {}) => {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    return node;
  };
  const formatTickTime = (time, hours) => {
    const date = new Date(time);
    if (hours <= 24) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (hours <= 168) return date.toLocaleDateString([], { weekday: "short", hour: "2-digit" });
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  };
  const nearestPoint = (values, targetTime) => {
    if (!values?.length) return null;
    let low = 0;
    let high = values.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (values[mid].time < targetTime) low = mid + 1;
      else high = mid;
    }
    const right = values[low];
    const left = values[Math.max(0, low - 1)];
    return Math.abs((left?.time ?? Infinity) - targetTime) <= Math.abs((right?.time ?? Infinity) - targetTime) ? left : right;
  };

  const install = async () => {
    if (typeof customElements === "undefined") return;
    await customElements.whenDefined("meshcore-noc-history-chart");
    const Chart = customElements.get("meshcore-noc-history-chart");
    if (!Chart || Chart.prototype.__telemetryChartV11Patched) return;
    Chart.prototype.__telemetryChartV11Patched = true;

    const originalSetConfig = Chart.prototype.setConfig;
    const originalRenderMessage = Chart.prototype._renderMessage;

    Chart.prototype._ensureV11ChartUi = function () {
      if (!this.shadowRoot) return;
      if (!this.shadowRoot.querySelector("style[data-v11-chart-style]")) {
        const style = document.createElement("style");
        style.dataset.v11ChartStyle = "true";
        style.textContent = `
.chart{position:relative;min-height:372px!important}
.chart-refresh{display:inline-flex;align-items:center;gap:5px;margin-top:4px;color:#7f8b95;font-size:.66rem}
.chart-refresh[data-state="updating"]{color:#4da3ff}
.plot{position:relative!important;min-height:290px!important}
.plot svg{height:290px!important}
.axis-time{fill:#8f9aa4;font-size:9.5px}
.series{stroke-width:2.25px!important}
.latest-point{stroke:#1a2128;stroke-width:2}
.hover-line{stroke:rgba(255,255,255,.28);stroke-width:1;stroke-dasharray:4 4;pointer-events:none}
.hover-overlay{fill:transparent;pointer-events:all;cursor:crosshair}
.chart-tooltip{position:absolute;z-index:4;display:none;min-width:180px;max-width:240px;padding:8px 9px;border:1px solid rgba(255,255,255,.13);border-radius:9px;background:rgba(13,17,21,.96);box-shadow:0 8px 24px #0008;color:#f3f6f8;font-size:.68rem;pointer-events:none}
.chart-tooltip strong{display:block;margin-bottom:5px;font-size:.7rem}
.tooltip-row{display:grid;grid-template-columns:9px minmax(0,1fr) auto;align-items:center;gap:6px;margin-top:3px}
.tooltip-dot{width:8px;height:8px;border-radius:50%}
.legend{gap:6px!important;margin-top:9px!important}
.legend button{display:flex;align-items:center;gap:6px;padding:5px 7px;border:1px solid rgba(255,255,255,.08);border-radius:8px;background:#202832;color:#c9d2d9;cursor:pointer;font:inherit;font-size:.68rem}
.legend button:hover{border-color:rgba(255,255,255,.2)}
.legend button[aria-pressed="false"]{opacity:.43}
.legend .legend-value{font-weight:800;color:#f3f6f8;font-variant-numeric:tabular-nums}
.legend .legend-delta{color:#8f9aa4;font-size:.62rem}
.chart-update-error{color:#f6c344}
@container(max-width:700px){.plot svg{height:245px!important}.chart{min-height:330px!important}.legend button{padding:4px 6px}}
`;
        this.shadowRoot.prepend(style);
      }
      const ranges = this.shadowRoot.querySelector(".ranges");
      if (ranges && !ranges.querySelector('[data-hours="6"]')) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.hours = "6";
        button.textContent = "6 h";
        ranges.prepend(button);
      }
      const subtitle = this.shadowRoot.querySelector(".subtitle");
      if (subtitle) subtitle.textContent = "Calibrated voltage · Recorder history · background refresh";
      const headerText = this.shadowRoot.querySelector("header > div");
      if (headerText && !headerText.querySelector(".chart-refresh")) {
        const refresh = document.createElement("div");
        refresh.className = "chart-refresh";
        refresh.dataset.state = "idle";
        refresh.textContent = "History ready";
        headerText.append(refresh);
      }
    };

    Chart.prototype._setV11RefreshState = function (text, state = "idle") {
      const node = this.shadowRoot?.querySelector(".chart-refresh");
      if (!node) return;
      node.dataset.state = state;
      node.textContent = text;
      node.classList.toggle("chart-update-error", state === "error");
    };

    Chart.prototype.setConfig = function (config) {
      originalSetConfig.call(this, config);
      this._ensureV11ChartUi();
    };

    Chart.prototype._renderMessage = function (message, error = false) {
      this._ensureV11ChartUi();
      const hasChart = Boolean(this.shadowRoot?.querySelector(".plot svg"));
      const loading = /^Loading\b/i.test(String(message || ""));
      if (hasChart && loading) {
        this._setV11RefreshState("Updating history…", "updating");
        return;
      }
      if (hasChart && error) {
        this._setV11RefreshState("Refresh failed · showing last good history", "error");
        return;
      }
      originalRenderMessage.call(this, message, error);
      this._setV11RefreshState(error ? "History unavailable" : String(message || ""), error ? "error" : "idle");
    };

    Chart.prototype._renderHistory = function (series, history) {
      this._ensureV11ChartUi();
      this._lastV11History = { series, history };
      this._hiddenV11Series = this._hiddenV11Series || new Set();

      const byEntity = new Map(
        history
          .filter((states) => Array.isArray(states) && states.length)
          .map((states) => [states[0].entity_id, states]),
      );
      const points = series.map((item, seriesIndex) => {
        const result = [];
        let invalidGap = false;
        let previous = null;
        for (const state of byEntity.get(item.entity) || []) {
          const rawTime = state.last_changed || state.last_updated || state.lu;
          const numericTime = Number(rawTime);
          const time = Number.isFinite(numericTime)
            ? numericTime < 1_000_000_000_000 ? numericTime * 1000 : numericTime
            : new Date(rawTime).getTime();
          const rawValue = state.state ?? state.s;
          const value = rawValue === null || rawValue === undefined || rawValue === "" || ["unknown", "unavailable"].includes(String(rawValue).toLowerCase())
            ? Number.NaN
            : Number(rawValue);
          if (!Number.isFinite(time) || !Number.isFinite(value) || value < 0 || value > 10) {
            invalidGap = true;
            continue;
          }
          const discontinuity = previous && Math.abs(value - previous.value) >= 0.35 && time - previous.time <= 15 * 60 * 1000;
          const point = { time, value, gapBefore: invalidGap || Boolean(discontinuity) };
          result.push(point);
          previous = point;
          invalidGap = false;
        }
        return { ...item, seriesIndex, values: result };
      });

      const visible = points.filter((item) => item.values.length && !this._hiddenV11Series.has(item.entity));
      const all = visible.flatMap((item) => item.values);
      if (!points.some((item) => item.values.length)) {
        originalRenderMessage.call(this, "No valid calibrated voltage history in this range.");
        this._setV11RefreshState("No valid recorder history", "idle");
        return;
      }

      const width = 1000;
      const height = 290;
      const pad = { left: 50, right: 18, top: 14, bottom: 34 };
      const minTime = Date.now() - this._rangeHours * 60 * 60 * 1000;
      const maxTime = Date.now();
      const values = all.length ? all.map((item) => item.value) : points.flatMap((item) => item.values).map((item) => item.value);
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const margin = Math.max(0.04, (rawMax - rawMin) * 0.12);
      let minValue = Math.max(0, Math.floor((rawMin - margin) * 20) / 20);
      let maxValue = Math.ceil((rawMax + margin) * 20) / 20;
      if (!(maxValue > minValue)) { minValue = Math.max(0, rawMin - 0.1); maxValue = rawMax + 0.1; }
      const x = (time) => pad.left + ((time - minTime) / (maxTime - minTime)) * (width - pad.left - pad.right);
      const y = (value) => pad.top + ((maxValue - value) / (maxValue - minValue)) * (height - pad.top - pad.bottom);

      const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${this._config?.title || "Voltage"} history` });
      for (let index = 0; index <= 4; index += 1) {
        const value = minValue + ((maxValue - minValue) * index) / 4;
        const lineY = y(value);
        svg.append(svgNode("line", { class: "grid-line", x1: pad.left, x2: width - pad.right, y1: lineY, y2: lineY }));
        const label = svgNode("text", { class: "axis-label", x: 2, y: lineY + 4 });
        label.textContent = `${value.toFixed(2)} V`;
        svg.append(label);
      }
      for (let index = 0; index <= 4; index += 1) {
        const time = minTime + ((maxTime - minTime) * index) / 4;
        const lineX = x(time);
        if (index > 0 && index < 4) svg.append(svgNode("line", { class: "grid-line", x1: lineX, x2: lineX, y1: pad.top, y2: height - pad.bottom }));
        const label = svgNode("text", { class: "axis-time", x: lineX, y: height - 8, "text-anchor": index === 0 ? "start" : index === 4 ? "end" : "middle" });
        label.textContent = index === 4 ? "Now" : formatTickTime(time, this._rangeHours);
        svg.append(label);
      }

      visible.forEach((item) => {
        const color = COLORS[item.seriesIndex % COLORS.length];
        const path = svgNode("path", { class: "series", stroke: color });
        path.setAttribute("d", item.values.map((point, pointIndex) => `${pointIndex && !point.gapBefore ? "L" : "M"}${x(point.time).toFixed(1)},${y(point.value).toFixed(1)}`).join(" "));
        svg.append(path);
        const last = item.values[item.values.length - 1];
        svg.append(svgNode("circle", { class: "latest-point", cx: x(last.time).toFixed(1), cy: y(last.value).toFixed(1), r: 4, fill: color }));
      });

      const crosshair = svgNode("line", { class: "hover-line", x1: 0, x2: 0, y1: pad.top, y2: height - pad.bottom, visibility: "hidden" });
      const overlay = svgNode("rect", { class: "hover-overlay", x: pad.left, y: pad.top, width: width - pad.left - pad.right, height: height - pad.top - pad.bottom });
      svg.append(crosshair, overlay);

      const plot = this.shadowRoot?.querySelector(".plot");
      const tooltip = document.createElement("div");
      tooltip.className = "chart-tooltip";
      plot?.replaceChildren(svg, tooltip);

      const legend = this.shadowRoot?.querySelector(".legend");
      legend?.replaceChildren();
      points.forEach((item) => {
        if (!item.values.length) return;
        const color = COLORS[item.seriesIndex % COLORS.length];
        const last = item.values[item.values.length - 1];
        const first = item.values[0];
        const delta = last.value - first.value;
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.entity = item.entity;
        button.setAttribute("aria-pressed", String(!this._hiddenV11Series.has(item.entity)));
        const swatch = document.createElement("i");
        swatch.className = "swatch";
        swatch.style.background = color;
        const name = document.createElement("span");
        name.textContent = item.name;
        const value = document.createElement("span");
        value.className = "legend-value";
        value.textContent = `${last.value.toFixed(2)} V`;
        const change = document.createElement("span");
        change.className = "legend-delta";
        change.textContent = `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`;
        button.append(swatch, name, value, change);
        button.addEventListener("click", () => {
          if (this._hiddenV11Series.has(item.entity)) this._hiddenV11Series.delete(item.entity);
          else this._hiddenV11Series.add(item.entity);
          const cached = this._lastV11History;
          if (cached) this._renderHistory(cached.series, cached.history);
        });
        legend?.append(button);
      });

      const showTooltip = (event) => {
        if (!plot || !visible.length) return;
        const rect = svg.getBoundingClientRect();
        const ratio = clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1);
        const svgX = ratio * width;
        if (svgX < pad.left || svgX > width - pad.right) return;
        const time = minTime + ((svgX - pad.left) / (width - pad.left - pad.right)) * (maxTime - minTime);
        const rows = visible.map((item) => ({ item, point: nearestPoint(item.values, time) })).filter((entry) => entry.point);
        if (!rows.length) return;
        crosshair.setAttribute("x1", svgX.toFixed(1));
        crosshair.setAttribute("x2", svgX.toFixed(1));
        crosshair.setAttribute("visibility", "visible");
        tooltip.replaceChildren();
        const heading = document.createElement("strong");
        heading.textContent = new Date(time).toLocaleString();
        tooltip.append(heading);
        rows.forEach(({ item, point }) => {
          const row = document.createElement("div");
          row.className = "tooltip-row";
          const dot = document.createElement("i");
          dot.className = "tooltip-dot";
          dot.style.background = COLORS[item.seriesIndex % COLORS.length];
          const name = document.createElement("span");
          name.textContent = item.name;
          const value = document.createElement("b");
          value.textContent = `${point.value.toFixed(3)} V`;
          row.append(dot, name, value);
          tooltip.append(row);
        });
        const plotRect = plot.getBoundingClientRect();
        tooltip.style.display = "block";
        const tooltipWidth = 220;
        tooltip.style.left = `${clamp(event.clientX - plotRect.left + 12, 8, Math.max(8, plotRect.width - tooltipWidth - 8))}px`;
        tooltip.style.top = "8px";
      };
      overlay.addEventListener("pointermove", showTooltip);
      overlay.addEventListener("pointerleave", () => {
        crosshair.setAttribute("visibility", "hidden");
        tooltip.style.display = "none";
      });

      this._setV11RefreshState(`Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`, "idle");
    };

    console.info("MeshCore NOC 1.1 telemetry chart patch loaded");
  };

  install().catch((error) => console.error("MeshCore NOC 1.1 telemetry chart patch failed", error));
})();
