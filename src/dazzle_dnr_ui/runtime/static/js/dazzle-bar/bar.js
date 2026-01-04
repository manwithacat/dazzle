// @ts-check
/**
 * Dazzle Bar - Main bar component for the developer overlay
 * Part of the Dazzle Native Runtime v0.8.5
 *
 * Renders the fixed bar at the top of the viewport with persona/scenario controls.
 *
 * @module dazzle-bar/bar
 */

import { createEffect } from "../signals.js";
import {
  isBarVisible,
  currentPersona,
  currentScenario,
  availablePersonas,
  availableScenarios,
  isLoading,
  error,
  fetchState,
  DazzleRuntime,
} from "./runtime.js";
import { initEmailPanel, toggleEmailPanel } from "./email-panel.js";
import { initHealthPanel, toggleHealthPanel } from "./health-panel.js";

// =============================================================================
// Constants
// =============================================================================

const BAR_HEIGHT = 42;
const BAR_ID = "dazzle-bar";

// =============================================================================
// Styles
// =============================================================================

const barStyles = `
  #${BAR_ID} {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: ${BAR_HEIGHT}px;
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    color: #e8e8e8;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    z-index: 999999;
    display: flex;
    align-items: center;
    padding: 0 12px;
    gap: 16px;
    border-bottom: 2px solid #0f3460;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    transform: translateY(0);
    transition: transform 0.2s ease-out;
  }

  #${BAR_ID}.hidden {
    transform: translateY(-100%);
  }

  #${BAR_ID} .dazzle-logo {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #e94560;
    font-weight: 600;
    font-size: 14px;
    user-select: none;
  }

  #${BAR_ID} .dazzle-logo-icon {
    font-size: 18px;
  }

  #${BAR_ID} .dazzle-divider {
    width: 1px;
    height: 24px;
    background: #0f3460;
  }

  #${BAR_ID} .dazzle-section {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  #${BAR_ID} .dazzle-label {
    color: #888;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  #${BAR_ID} .dazzle-select {
    background: #0f3460;
    border: 1px solid #1a1a2e;
    border-radius: 4px;
    color: #e8e8e8;
    padding: 4px 8px;
    font-size: 12px;
    cursor: pointer;
    min-width: 120px;
    outline: none;
  }

  #${BAR_ID} .dazzle-select:hover {
    border-color: #e94560;
  }

  #${BAR_ID} .dazzle-select:focus {
    border-color: #e94560;
    box-shadow: 0 0 0 2px rgba(233, 69, 96, 0.2);
  }

  #${BAR_ID} .dazzle-btn {
    background: #0f3460;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #e8e8e8;
    padding: 4px 10px;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: all 0.15s;
  }

  #${BAR_ID} .dazzle-btn:hover {
    background: #1a1a2e;
    border-color: #e94560;
  }

  #${BAR_ID} .dazzle-btn:active {
    transform: scale(0.98);
  }

  #${BAR_ID} .dazzle-btn.primary {
    background: #e94560;
    color: white;
  }

  #${BAR_ID} .dazzle-btn.primary:hover {
    background: #d63d56;
  }

  #${BAR_ID} .dazzle-btn.danger {
    color: #ff6b6b;
  }

  #${BAR_ID} .dazzle-btn.danger:hover {
    background: rgba(255, 107, 107, 0.1);
    border-color: #ff6b6b;
  }

  #${BAR_ID} .dazzle-spacer {
    flex: 1;
  }

  #${BAR_ID} .dazzle-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #888;
  }

  #${BAR_ID} .dazzle-status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
  }

  #${BAR_ID} .dazzle-status-dot.loading {
    background: #fbbf24;
    animation: dazzle-pulse 1s ease-in-out infinite;
  }

  #${BAR_ID} .dazzle-status-dot.error {
    background: #ef4444;
  }

  @keyframes dazzle-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  #${BAR_ID} .dazzle-toggle {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 4px;
    font-size: 16px;
    transition: color 0.15s;
  }

  #${BAR_ID} .dazzle-toggle:hover {
    color: #e8e8e8;
  }

  /* Feedback modal */
  .dazzle-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    z-index: 9999999;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .dazzle-modal {
    background: #1a1a2e;
    border-radius: 8px;
    padding: 20px;
    width: 400px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    border: 1px solid #0f3460;
  }

  .dazzle-modal h3 {
    margin: 0 0 16px 0;
    color: #e8e8e8;
    font-size: 16px;
  }

  .dazzle-modal textarea {
    width: 100%;
    height: 100px;
    background: #0f3460;
    border: 1px solid #1a1a2e;
    border-radius: 4px;
    color: #e8e8e8;
    padding: 8px;
    font-family: inherit;
    font-size: 13px;
    resize: vertical;
    outline: none;
    box-sizing: border-box;
  }

  .dazzle-modal textarea:focus {
    border-color: #e94560;
  }

  .dazzle-modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 16px;
  }

  .dazzle-modal .dazzle-btn {
    background: #0f3460;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #e8e8e8;
    padding: 8px 16px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .dazzle-modal .dazzle-btn:hover {
    background: #1a1a2e;
    border-color: #e94560;
  }

  .dazzle-modal .dazzle-btn.primary {
    background: #e94560;
    color: white;
  }

  .dazzle-modal .dazzle-btn.primary:hover {
    background: #d63d56;
  }

  .dazzle-category-select {
    margin-bottom: 12px;
  }

  /* Body padding when bar is visible */
  body.dazzle-bar-active {
    padding-top: ${BAR_HEIGHT}px !important;
  }

  /* =========================================================================
     Responsive Styles - Small Viewports
     ========================================================================= */

  @media (max-width: 768px) {
    #${BAR_ID} {
      padding: 0 8px;
      gap: 8px;
    }

    #${BAR_ID} .dazzle-logo span:not(.dazzle-logo-icon) {
      display: none;
    }

    #${BAR_ID} .dazzle-label {
      display: none;
    }

    #${BAR_ID} .dazzle-select {
      min-width: 100px;
      font-size: 11px;
      padding: 4px 6px;
    }

    #${BAR_ID} .dazzle-btn-text {
      display: none;
    }

    #${BAR_ID} .dazzle-btn {
      padding: 4px 8px;
    }

    #${BAR_ID} .dazzle-status .dazzle-status-text {
      display: none;
    }

    #${BAR_ID} .dazzle-divider:nth-of-type(2),
    #${BAR_ID} .dazzle-divider:nth-of-type(3) {
      display: none;
    }
  }

  @media (max-width: 540px) {
    #${BAR_ID} {
      flex-wrap: wrap;
      height: auto;
      min-height: ${BAR_HEIGHT}px;
      padding: 6px 8px;
      gap: 6px;
    }

    body.dazzle-bar-active {
      padding-top: 72px !important;
    }

    #${BAR_ID} .dazzle-section {
      gap: 4px;
    }

    #${BAR_ID} .dazzle-select {
      min-width: 80px;
    }

    #${BAR_ID} .dazzle-spacer {
      display: none;
    }

    #${BAR_ID} .dazzle-divider {
      display: none;
    }

    /* Move action buttons to second row */
    #${BAR_ID} .dazzle-section:nth-of-type(3) {
      order: 10;
    }

    #${BAR_ID} .dazzle-section:nth-of-type(4) {
      order: 11;
    }

    /* Hide less essential buttons */
    #${BAR_ID} #dazzle-regenerate-btn,
    #${BAR_ID} #dazzle-export-btn {
      display: none;
    }
  }

  @media (max-width: 380px) {
    #${BAR_ID} #dazzle-feedback-btn {
      display: none;
    }

    #${BAR_ID} .dazzle-select {
      min-width: 70px;
      font-size: 10px;
    }
  }
`;

// =============================================================================
// UI Rendering
// =============================================================================

/**
 * Create the bar element.
 * @returns {HTMLDivElement}
 */
function createBarElement() {
  const bar = document.createElement("div");
  bar.id = BAR_ID;
  // Add semantic attribute for E2E testing
  bar.setAttribute("data-dazzle-component", "dazzle-bar");

  bar.innerHTML = `
    <div class="dazzle-logo">
      <span class="dazzle-logo-icon">&#x2728;</span>
      <span>Dazzle</span>
    </div>

    <div class="dazzle-divider"></div>

    <div class="dazzle-section">
      <span class="dazzle-label">Persona</span>
      <select class="dazzle-select" id="dazzle-persona-select" data-dazzle-control="persona-select">
        <option value="">Select persona...</option>
      </select>
    </div>

    <div class="dazzle-section">
      <span class="dazzle-label">Scenario</span>
      <select class="dazzle-select" id="dazzle-scenario-select" data-dazzle-control="scenario-select">
        <option value="">Select scenario...</option>
      </select>
    </div>

    <div class="dazzle-divider"></div>

    <div class="dazzle-section">
      <button class="dazzle-btn danger" id="dazzle-reset-btn" title="Reset all data" data-dazzle-action="reset" data-dazzle-action-role="destructive">
        <span class="dazzle-btn-icon">&#x21bb;</span><span class="dazzle-btn-text">Reset</span>
      </button>
      <button class="dazzle-btn" id="dazzle-regenerate-btn" title="Regenerate demo data" data-dazzle-action="regenerate" data-dazzle-action-role="secondary">
        <span class="dazzle-btn-icon">&#x2699;</span><span class="dazzle-btn-text">Regen</span>
      </button>
    </div>

    <div class="dazzle-spacer"></div>

    <div class="dazzle-section">
      <button class="dazzle-btn" id="dazzle-email-btn" title="View email outbox" data-dazzle-action="email" data-dazzle-action-role="secondary">
        <span class="dazzle-btn-icon">&#x2709;</span><span class="dazzle-btn-text">Email</span>
      </button>
      <button class="dazzle-btn primary" id="dazzle-feedback-btn" data-dazzle-action="feedback" data-dazzle-action-role="primary">
        <span class="dazzle-btn-icon">&#x1F4AC;</span><span class="dazzle-btn-text">Feedback</span>
      </button>
      <button class="dazzle-btn" id="dazzle-export-btn" title="Export session to GitHub issue" data-dazzle-action="export" data-dazzle-action-role="secondary">
        <span class="dazzle-btn-icon">&#x1F4E4;</span><span class="dazzle-btn-text">Export</span>
      </button>
    </div>

    <div class="dazzle-divider"></div>

    <div id="dazzle-health-indicator" title="System health - click for details" data-dazzle-control="health">
      <span class="health-dot healthy"></span>
      <span class="health-label">Healthy</span>
    </div>

    <div class="dazzle-status" data-dazzle-control="status">
      <span class="dazzle-status-dot" id="dazzle-status-dot"></span>
      <span class="dazzle-status-text" id="dazzle-status-text">Dev Mode</span>
    </div>

    <button class="dazzle-toggle" id="dazzle-hide-btn" title="Hide bar (Cmd+Shift+D)" data-dazzle-action="hide-bar">
      &#x2715;
    </button>
  `;

  return bar;
}

/**
 * Inject styles into the document.
 */
function injectStyles() {
  if (document.getElementById("dazzle-bar-styles")) return;

  const style = document.createElement("style");
  style.id = "dazzle-bar-styles";
  style.textContent = barStyles;
  document.head.appendChild(style);
}

/**
 * Update the persona select options.
 */
function updatePersonaSelect() {
  const select = /** @type {HTMLSelectElement|null} */ (
    document.getElementById("dazzle-persona-select")
  );
  if (!select) return;

  const personas = availablePersonas();
  const current = currentPersona();

  select.innerHTML =
    '<option value="">Select persona...</option>' +
    personas
      .map(
        (p) =>
          `<option value="${p.id}" ${p.id === current ? "selected" : ""}>${p.label || p.id}</option>`,
      )
      .join("");
}

/**
 * Update the scenario select options.
 */
function updateScenarioSelect() {
  const select = /** @type {HTMLSelectElement|null} */ (
    document.getElementById("dazzle-scenario-select")
  );
  if (!select) return;

  const scenarios = availableScenarios();
  const current = currentScenario();

  select.innerHTML =
    '<option value="">Select scenario...</option>' +
    scenarios
      .map(
        (s) =>
          `<option value="${s.id}" ${s.id === current ? "selected" : ""}>${s.name || s.id}</option>`,
      )
      .join("");
}

/**
 * Update the status indicator.
 */
function updateStatus() {
  const dot = document.getElementById("dazzle-status-dot");
  const text = document.getElementById("dazzle-status-text");
  if (!dot || !text) return;

  const loading = isLoading();
  const err = error();

  dot.classList.toggle("loading", loading);
  dot.classList.toggle("error", !!err);

  if (err) {
    text.textContent = "Error";
    text.title = err;
  } else if (loading) {
    text.textContent = "Loading...";
    text.title = "";
  } else {
    text.textContent = "Dev Mode";
    text.title = "";
  }
}

/**
 * Show the feedback modal.
 */
function showFeedbackModal() {
  // Remove existing modal if any
  const existing = document.querySelector(".dazzle-modal-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.className = "dazzle-modal-overlay";
  overlay.innerHTML = `
    <div class="dazzle-modal">
      <h3>&#x1F4AC; Send Feedback</h3>
      <div class="dazzle-category-select">
        <select class="dazzle-select" id="dazzle-feedback-category" style="width: 100%">
          <option value="general">General Feedback</option>
          <option value="bug">Bug Report</option>
          <option value="feature">Feature Request</option>
          <option value="ux">UX Issue</option>
        </select>
      </div>
      <textarea id="dazzle-feedback-text" placeholder="Describe your feedback..."></textarea>
      <div class="dazzle-modal-actions">
        <button class="dazzle-btn" id="dazzle-feedback-cancel">Cancel</button>
        <button class="dazzle-btn primary" id="dazzle-feedback-submit">Submit</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Focus the textarea
  const textarea = /** @type {HTMLTextAreaElement|null} */ (
    document.getElementById("dazzle-feedback-text")
  );
  if (textarea) textarea.focus();

  // Close on overlay click
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  // Cancel button
  const cancelBtn = document.getElementById("dazzle-feedback-cancel");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => overlay.remove());
  }

  // Submit button
  const submitBtn = document.getElementById("dazzle-feedback-submit");
  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      const category = /** @type {HTMLSelectElement|null} */ (
        document.getElementById("dazzle-feedback-category")
      )?.value;
      const message = textarea?.value?.trim();

      if (!message) {
        textarea?.focus();
        return;
      }

      try {
        const result = await DazzleRuntime.submitFeedback({
          message,
          category: category || "general",
        });
        overlay.remove();
        // Show success toast with email status indicator
        const emailSent = result.status === "logged_and_emailed";
        const toastMessage = emailSent
          ? "✓ Feedback submitted and emailed to developer"
          : "✓ Feedback logged (email not configured)";
        showToast(toastMessage, "success");
      } catch (_err) {
        showToast("Failed to submit feedback", "error");
      }
    });
  }

  // Close on Escape
  const handleEscape = (/** @type {KeyboardEvent} */ e) => {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", handleEscape);
    }
  };
  document.addEventListener("keydown", handleEscape);
}

/**
 * Show a toast notification.
 * @param {string} message - Toast message
 * @param {'success'|'error'|'info'} [type='info'] - Toast type
 */
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    background: ${type === "success" ? "#4ade80" : type === "error" ? "#ef4444" : "#3b82f6"};
    color: white;
    border-radius: 6px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    z-index: 99999999;
    animation: dazzle-toast-in 0.2s ease-out;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  `;
  toast.textContent = message;

  // Add animation keyframes if not present
  if (!document.getElementById("dazzle-toast-styles")) {
    const style = document.createElement("style");
    style.id = "dazzle-toast-styles";
    style.textContent = `
      @keyframes dazzle-toast-in {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }

  document.body.appendChild(toast);

  // Auto-remove after 3 seconds
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.2s ease-out";
    setTimeout(() => toast.remove(), 200);
  }, 3000);
}

// =============================================================================
// Event Handlers
// =============================================================================

/**
 * Set up event handlers for the bar.
 */
function setupEventHandlers() {
  // Persona select
  const personaSelect = document.getElementById("dazzle-persona-select");
  if (personaSelect) {
    personaSelect.addEventListener("change", async (e) => {
      const value = /** @type {HTMLSelectElement} */ (e.target).value;
      if (value) {
        await DazzleRuntime.setPersona(value);
      }
    });
  }

  // Scenario select
  const scenarioSelect = document.getElementById("dazzle-scenario-select");
  if (scenarioSelect) {
    scenarioSelect.addEventListener("change", async (e) => {
      const value = /** @type {HTMLSelectElement} */ (e.target).value;
      if (value) {
        await DazzleRuntime.setScenario(value);
      }
    });
  }

  // Reset button
  const resetBtn = document.getElementById("dazzle-reset-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      if (
        confirm(
          "Are you sure you want to reset all data? This cannot be undone.",
        )
      ) {
        await DazzleRuntime.resetData();
      }
    });
  }

  // Regenerate button
  const regenerateBtn = document.getElementById("dazzle-regenerate-btn");
  if (regenerateBtn) {
    regenerateBtn.addEventListener("click", async () => {
      await DazzleRuntime.regenerateData();
    });
  }

  // Email button
  const emailBtn = document.getElementById("dazzle-email-btn");
  if (emailBtn) {
    emailBtn.addEventListener("click", toggleEmailPanel);
  }

  // Health indicator
  const healthIndicator = document.getElementById("dazzle-health-indicator");
  if (healthIndicator) {
    healthIndicator.addEventListener("click", toggleHealthPanel);
  }

  // Feedback button
  const feedbackBtn = document.getElementById("dazzle-feedback-btn");
  if (feedbackBtn) {
    feedbackBtn.addEventListener("click", showFeedbackModal);
  }

  // Export button
  const exportBtn = document.getElementById("dazzle-export-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", async () => {
      try {
        await DazzleRuntime.exportSession("github_issue");
        showToast("Export link opened in new tab", "success");
      } catch (_err) {
        showToast("Failed to export session", "error");
      }
    });
  }

  // Hide button
  const hideBtn = document.getElementById("dazzle-hide-btn");
  if (hideBtn) {
    hideBtn.addEventListener("click", () => {
      DazzleRuntime.hideBar();
    });
  }

  // Keyboard shortcut: Cmd+Shift+D to toggle bar
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "D") {
      e.preventDefault();
      DazzleRuntime.toggleBar();
    }
  });
}

// =============================================================================
// Initialization
// =============================================================================

let initialized = false;

/**
 * Initialize the Dazzle Bar.
 * Call this to enable the bar in development mode.
 */
export function initDazzleBar() {
  if (initialized) return;
  initialized = true;

  // Inject styles
  injectStyles();

  // Create and append bar
  const bar = createBarElement();
  document.body.appendChild(bar);

  // Add body padding class
  document.body.classList.add("dazzle-bar-active");

  // Set up event handlers
  setupEventHandlers();

  // Initialize email panel
  initEmailPanel();

  // Initialize health panel
  initHealthPanel();

  // Set up reactive updates
  createEffect(() => {
    const visible = isBarVisible();
    bar.classList.toggle("hidden", !visible);
    document.body.classList.toggle("dazzle-bar-active", visible);
  });

  createEffect(() => {
    availablePersonas();
    updatePersonaSelect();
  });

  createEffect(() => {
    currentPersona();
    updatePersonaSelect();
  });

  createEffect(() => {
    availableScenarios();
    updateScenarioSelect();
  });

  createEffect(() => {
    currentScenario();
    updateScenarioSelect();
  });

  createEffect(() => {
    isLoading();
    error();
    updateStatus();
  });

  // Fetch initial state
  fetchState().catch((err) => {
    console.warn("[Dazzle Bar] Failed to fetch initial state:", err);
  });

  console.log("[Dazzle Bar] Initialized. Press Cmd+Shift+D to toggle.");
}

export { BAR_HEIGHT, BAR_ID, showToast };
