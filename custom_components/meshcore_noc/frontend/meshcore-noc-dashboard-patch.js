/* MeshCore NOC clock-sync UX patch. Loaded after the bundled dashboard. */
(() => {
  "use strict";

  const PATCH_MARKER = "__meshcoreNocClockSyncUxPatch";
  if (globalThis[PATCH_MARKER]) return;
  globalThis[PATCH_MARKER] = true;

  const describeError = (error) => {
    const candidates = [
      error?.message,
      error?.error,
      error?.code,
      typeof error === "string" ? error : null,
    ].filter(Boolean);
    const message = String(candidates[0] || "").trim();
    if (
      !message ||
      message.toLowerCase() === "unknown error" ||
      message === "[object Object]"
    )
      return "Home Assistant rejected the password request. Check Settings → System → Logs for the detailed error.";
    return message;
  };

  const findPanel = (fragment, heading) =>
    Array.from(fragment.querySelectorAll?.("section.detail-panel") || []).find(
      (panel) => panel.querySelector("h2")?.textContent?.trim() === heading,
    ) || null;

  const replaceClockSourceWarning = (root) => {
    for (const node of root?.querySelectorAll?.(".source-warning,.clock-health.warning") || []) {
      if (node.textContent?.includes("connected MeshCore companion clock"))
        node.textContent =
          "Clock synchronisation uses the Home Assistant UTC system clock. Home Assistant should have working internet/NTP time synchronisation.";
    }
    return root;
  };

  const install = async () => {
    if (typeof customElements === "undefined") return;
    await customElements.whenDefined("meshcore-noc-overview-card");
    const Card = customElements.get("meshcore-noc-overview-card");
    if (!Card || Card.prototype.__clockSyncUxPatched) return;
    Card.prototype.__clockSyncUxPatched = true;

    const originalDetailView = Card.prototype._detailView;
    const originalCombinedHeader = Card.prototype._combinedHeader;
    const originalFleetClockSection = Card.prototype._fleetClockSection;
    const originalHandleAction = Card.prototype._handleAction;
    const originalManagementAction = Card.prototype._handleManagementAction;

    Card.prototype._ensureClockSyncPatchStyle = function () {
      if (!this.shadowRoot || this.shadowRoot.querySelector("style[data-clock-sync-patch]"))
        return;
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
`;
      this.shadowRoot.prepend(style);
    };

    Card.prototype._combinedHeader = function (...args) {
      return replaceClockSourceWarning(originalCombinedHeader.call(this, ...args));
    };

    Card.prototype._fleetClockSection = function (...args) {
      return replaceClockSourceWarning(originalFleetClockSection.call(this, ...args));
    };

    Card.prototype._detailView = function (...args) {
      const fragment = originalDetailView.call(this, ...args);
      const repeater = args[0];
      if (!repeater) return fragment;
      this._ensureClockSyncPatchStyle();

      const clockPanel = findPanel(fragment, "Repeater clock");
      const accessPanel = findPanel(fragment, "Repeater access");
      if (clockPanel && accessPanel && clockPanel.parentNode === accessPanel.parentNode)
        clockPanel.after(accessPanel);

      if (!clockPanel) return fragment;
      const settings = this._managementFor(repeater.stableId);
      const accessState = this._element(
        "div",
        `sync-access-state ${settings.password_configured ? "healthy" : "warning"}`,
        settings.password_configured
          ? "Repeater access ✓ Administrator password is saved for clock synchronisation."
          : "Repeater access required: save the administrator password below before using Sync this repeater.",
      );
      clockPanel.append(accessState);

      const clockState = this._hass?.states?.[repeater.entities.clockStatus];
      const attributes = clockState?.attributes || {};
      const transcript = String(attributes.last_sync_response || "").trim();
      if (transcript) {
        const log = this._element(
          "div",
          `sync-live-log${attributes.sync_running ? " running" : ""}`,
        );
        log.append(
          this._element(
            "strong",
            "",
            attributes.sync_running ? "Clock sync — working…" : "Last clock sync activity",
          ),
        );
        const lines = transcript.split("\n").filter(Boolean).slice(-20);
        for (const line of lines)
          log.append(this._element("div", "sync-line", line));
        clockPanel.append(log);
      }
      return fragment;
    };

    Card.prototype._handleAction = async function (event) {
      const button = event.target?.closest?.("[data-entity-id],[data-service]");
      if (button?.dataset?.actionKind === "repeater-sync") {
        let data = {};
        try {
          data = JSON.parse(button.dataset.serviceData || "{}");
        } catch (_error) {
          data = {};
        }
        const stableId = data.repeater_id;
        const settings = stableId ? this._managementFor(stableId) : null;
        if (stableId && !settings?.password_configured) {
          this._managementMessages = this._managementMessages || new Map();
          this._managementMessages.set(stableId, {
            text: "Password required. Enter and save the repeater administrator password before clock synchronisation.",
            error: true,
          });
          this._showFeedback(
            "Clock sync not started — repeater administrator password is required.",
            true,
          );
          this._render("clock-sync-password-required");
          setTimeout(() => {
            const input = Array.from(
              this.shadowRoot?.querySelectorAll("[data-password-input]") || [],
            ).find((item) => item.dataset.stableId === stableId);
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
      if (
        !button ||
        !["password-save", "password-remove"].includes(
          button.dataset.managementAction,
        )
      )
        return originalManagementAction.call(this, event);
      if (button.disabled) return;

      const stableId = button.dataset.stableId;
      const action = button.dataset.managementAction;
      const saved = this._managementFor(stableId);
      button.disabled = true;
      try {
        if (!this._hass?.callWS)
          throw new Error("Home Assistant management API unavailable");

        let result;
        if (action === "password-save") {
          const passwordInput = Array.from(
            this.shadowRoot?.querySelectorAll("[data-password-input]") || [],
          ).find((item) => item.dataset.stableId === stableId);
          const password = passwordInput?.value || "";
          if (!password) {
            this._managementMessages.set(stableId, {
              text: "Enter the repeater administrator password first.",
              error: true,
            });
            this._render("password-empty");
            return;
          }
          result = await this._hass.callWS({
            type: "meshcore_noc/management/set_password",
            stable_id: stableId,
            password,
          });
          if (!result || result.password_configured !== true)
            throw new Error("Password save was not confirmed by MeshCore NOC.");
          if (passwordInput) passwordInput.value = "";
        } else {
          result = await this._hass.callWS({
            type: "meshcore_noc/management/remove_password",
            stable_id: stableId,
          });
        }

        this._managementSettings.set(stableId, { ...saved, ...result });
        this._managementMessages.set(stableId, {
          text:
            action === "password-save"
              ? "Password saved. Clock synchronisation can now authenticate to this repeater."
              : "Repeater password removed. Clock synchronisation will require a password before it can run.",
          error: false,
        });
      } catch (error) {
        this._managementMessages.set(stableId, {
          text: `Password action failed: ${describeError(error)}`,
          error: true,
        });
      } finally {
        button.disabled = false;
        this._render("password-action-completed");
      }
    };

    console.info("MeshCore NOC clock-sync UX patch loaded");
  };

  install().catch((error) =>
    console.error("MeshCore NOC clock-sync UX patch failed", error),
  );
})();
