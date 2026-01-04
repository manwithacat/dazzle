// @ts-check
/**
 * Dazzle Bar - Health Panel Component
 * Shows system health status in an expandable panel.
 *
 * @module dazzle-bar/health-panel
 */

import { createSignal, createEffect } from "../signals.js";

// =============================================================================
// State
// =============================================================================

/** @type {import('../signals.js').Signal<boolean>} */
const [isHealthPanelOpen, setHealthPanelOpen] = createSignal(false);

/** @type {import('../signals.js').Signal<HealthStatus | null>} */
const [healthStatus, setHealthStatus] = createSignal(
  /** @type {HealthStatus | null} */ (null),
);

/** @type {import('../signals.js').Signal<boolean>} */
const [isHealthLoading, setHealthLoading] = createSignal(false);

/**
 * @typedef {Object} ComponentHealth
 * @property {string} name - Component name
 * @property {'healthy' | 'degraded' | 'unhealthy'} status - Health status
 * @property {number} [latency_ms] - Response latency in ms
 * @property {string} [message] - Status message
 */

/**
 * @typedef {Object} HealthStatus
 * @property {'healthy' | 'degraded' | 'unhealthy'} overall - Overall status
 * @property {ComponentHealth[]} components - Component statuses
 * @property {string} checked_at - ISO timestamp
 */

// =============================================================================
// Styles
// =============================================================================

const healthPanelStyles = `
  #dazzle-health-panel {
    position: fixed;
    top: 50px;
    right: 12px;
    width: 280px;
    background: #1a1a2e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 9999998;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    color: #e8e8e8;
    transform: translateY(-10px);
    opacity: 0;
    pointer-events: none;
    transition: transform 0.15s ease-out, opacity 0.15s ease-out;
  }

  #dazzle-health-panel.open {
    transform: translateY(0);
    opacity: 1;
    pointer-events: auto;
  }

  .health-panel-header {
    padding: 12px 16px;
    border-bottom: 1px solid #0f3460;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .health-panel-title {
    font-weight: 600;
    font-size: 14px;
  }

  .health-panel-refresh {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 4px;
    font-size: 14px;
    transition: color 0.15s;
  }

  .health-panel-refresh:hover {
    color: #e8e8e8;
  }

  .health-panel-refresh.loading {
    animation: health-spin 1s linear infinite;
  }

  @keyframes health-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .health-panel-body {
    padding: 12px 16px;
    max-height: 300px;
    overflow-y: auto;
  }

  .health-component {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #0f3460;
  }

  .health-component:last-child {
    border-bottom: none;
  }

  .health-component-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .health-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .health-dot.healthy {
    background: #4ade80;
  }

  .health-dot.degraded {
    background: #fbbf24;
  }

  .health-dot.unhealthy {
    background: #ef4444;
  }

  .health-component-name {
    font-weight: 500;
  }

  .health-component-latency {
    color: #888;
    font-size: 11px;
  }

  .health-panel-footer {
    padding: 12px 16px;
    border-top: 1px solid #0f3460;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .health-panel-footer a {
    color: #e94560;
    text-decoration: none;
    font-size: 12px;
  }

  .health-panel-footer a:hover {
    text-decoration: underline;
  }

  .health-updated {
    color: #666;
    font-size: 11px;
  }

  /* Health indicator in bar */
  #dazzle-health-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
    transition: background 0.15s;
  }

  #dazzle-health-indicator:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  #dazzle-health-indicator .health-dot {
    width: 10px;
    height: 10px;
  }

  #dazzle-health-indicator .health-label {
    font-size: 12px;
    color: #888;
  }
`;

// =============================================================================
// API
// =============================================================================

/**
 * Fetch system health status from the server.
 * @returns {Promise<HealthStatus>}
 */
async function fetchHealthStatus() {
  try {
    const response = await fetch("/dazzle/dev/health");
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    // Return degraded status on error
    return {
      overall: "unhealthy",
      components: [
        { name: "API", status: "unhealthy", message: String(error) },
      ],
      checked_at: new Date().toISOString(),
    };
  }
}

// =============================================================================
// UI
// =============================================================================

/**
 * Create and inject the health panel styles.
 */
function injectHealthStyles() {
  if (document.getElementById("dazzle-health-panel-styles")) return;

  const style = document.createElement("style");
  style.id = "dazzle-health-panel-styles";
  style.textContent = healthPanelStyles;
  document.head.appendChild(style);
}

/**
 * Create the health panel element.
 * @returns {HTMLDivElement}
 */
function createHealthPanel() {
  const panel = document.createElement("div");
  panel.id = "dazzle-health-panel";
  panel.innerHTML = `
    <div class="health-panel-header">
      <span class="health-panel-title">System Health</span>
      <button class="health-panel-refresh" id="health-refresh-btn" title="Refresh">&#x21bb;</button>
    </div>
    <div class="health-panel-body" id="health-panel-body">
      <div style="text-align: center; color: #888; padding: 20px;">
        Loading...
      </div>
    </div>
    <div class="health-panel-footer">
      <a href="/dazzle/dev/dashboard" target="_blank">Open Dashboard</a>
      <span class="health-updated" id="health-updated"></span>
    </div>
  `;
  return panel;
}

/**
 * Update the panel body with health status.
 * @param {HealthStatus | null} status
 */
function updateHealthPanelBody(status) {
  const body = document.getElementById("health-panel-body");
  const updated = document.getElementById("health-updated");
  if (!body) return;

  if (!status) {
    body.innerHTML = `
      <div style="text-align: center; color: #888; padding: 20px;">
        Loading...
      </div>
    `;
    return;
  }

  const componentsHtml = status.components
    .map(
      (c) => `
    <div class="health-component">
      <div class="health-component-info">
        <span class="health-dot ${c.status}"></span>
        <span class="health-component-name">${c.name}</span>
      </div>
      <span class="health-component-latency">${c.latency_ms ? `${c.latency_ms}ms` : c.message || ""}</span>
    </div>
  `,
    )
    .join("");

  body.innerHTML =
    componentsHtml ||
    `
    <div style="text-align: center; color: #888; padding: 20px;">
      No components found
    </div>
  `;

  if (updated && status.checked_at) {
    const time = new Date(status.checked_at);
    updated.textContent = `Updated ${time.toLocaleTimeString()}`;
  }
}

/**
 * Update the health indicator in the bar.
 * @param {HealthStatus | null} status
 */
function updateHealthIndicator(status) {
  const indicator = document.getElementById("dazzle-health-indicator");
  if (!indicator) return;

  const dot = indicator.querySelector(".health-dot");
  const label = indicator.querySelector(".health-label");

  if (dot) {
    dot.classList.remove("healthy", "degraded", "unhealthy");
    dot.classList.add(status?.overall || "healthy");
  }

  if (label) {
    if (status?.overall === "healthy") {
      label.textContent = "Healthy";
    } else if (status?.overall === "degraded") {
      label.textContent = "Degraded";
    } else if (status?.overall === "unhealthy") {
      label.textContent = "Unhealthy";
    } else {
      label.textContent = "Checking...";
    }
  }
}

/**
 * Refresh health status.
 */
async function refreshHealth() {
  const refreshBtn = document.getElementById("health-refresh-btn");
  if (refreshBtn) refreshBtn.classList.add("loading");

  setHealthLoading(true);

  try {
    const status = await fetchHealthStatus();
    setHealthStatus(status);
  } finally {
    setHealthLoading(false);
    if (refreshBtn) refreshBtn.classList.remove("loading");
  }
}

/**
 * Toggle the health panel visibility.
 */
export function toggleHealthPanel() {
  const panel = document.getElementById("dazzle-health-panel");
  const isOpen = isHealthPanelOpen();

  if (!isOpen) {
    // Fetch fresh data when opening
    refreshHealth();
  }

  setHealthPanelOpen(!isOpen);
  if (panel) {
    panel.classList.toggle("open", !isOpen);
  }
}

/**
 * Initialize the health panel.
 * Should be called from the main bar initialization.
 */
export function initHealthPanel() {
  injectHealthStyles();

  // Create panel
  const panel = createHealthPanel();
  document.body.appendChild(panel);

  // Set up refresh button
  const refreshBtn = document.getElementById("health-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshHealth);
  }

  // Close panel when clicking outside
  document.addEventListener("click", (e) => {
    const panel = document.getElementById("dazzle-health-panel");
    const indicator = document.getElementById("dazzle-health-indicator");
    const target = /** @type {Node} */ (e.target);

    if (isHealthPanelOpen() && panel && indicator) {
      if (!panel.contains(target) && !indicator.contains(target)) {
        setHealthPanelOpen(false);
        panel.classList.remove("open");
      }
    }
  });

  // Reactive update when status changes
  createEffect(() => {
    const status = healthStatus();
    updateHealthPanelBody(status);
    updateHealthIndicator(status);
  });

  // Initial health check
  refreshHealth();
}

export { isHealthPanelOpen, healthStatus, isHealthLoading };
