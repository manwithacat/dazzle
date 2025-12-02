// @ts-check
/**
 * DNR-UI DevTools - Browser development tools panel
 * Part of the Dazzle Native Runtime
 *
 * Provides state inspection, network request logging, and debugging utilities.
 *
 * @module devtools
 */

import { createSignal, createEffect } from './signals.js';
import { stateStores } from './state.js';
import { apiClient } from './api-client.js';
import { setActionLogger } from './actions.js';

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @typedef {Object} NetworkRequest
 * @property {string} id - Request ID
 * @property {string} method - HTTP method
 * @property {string} url - Request URL
 * @property {number} startTime - Timestamp when request started
 * @property {number} [endTime] - Timestamp when request completed
 * @property {number} [duration] - Duration in ms
 * @property {'pending'|'success'|'error'} status - Request status
 * @property {number} [statusCode] - HTTP status code
 * @property {any} [requestBody] - Request body
 * @property {any} [responseBody] - Response body
 * @property {string} [error] - Error message
 */

/**
 * @typedef {'state'|'network'|'actions'} DevToolsTab
 */

// =============================================================================
// State
// =============================================================================

const [isOpen, setIsOpen] = createSignal(/** @type {boolean} */ (false));

// Use type assertion for the full union type
const [activeTab, setActiveTab] = createSignal(/** @type {DevToolsTab} */ ('state'));

/** @type {NetworkRequest[]} */
const initialRequests = [];
const [networkRequests, setNetworkRequests] = createSignal(initialRequests);

/** @type {string[]} */
const initialActions = [];
const [actionLog, setActionLog] = createSignal(initialActions);

let requestCounter = 0;

// =============================================================================
// Network Request Interceptor
// =============================================================================

/**
 * Wrap the apiClient to intercept and log all requests.
 */
function interceptNetworkRequests() {
  const originalRequest = apiClient.request.bind(apiClient);

  apiClient.request = async function (method, path, data = null, options = {}) {
    const id = `req-${++requestCounter}`;
    const url = `${apiClient.baseUrl}${path}`;
    const startTime = Date.now();

    /** @type {NetworkRequest} */
    const request = {
      id,
      method,
      url,
      startTime,
      status: 'pending',
      requestBody: data
    };

    const currentReqs = networkRequests();
    setNetworkRequests([request, ...currentReqs].slice(0, 50)); // Keep last 50

    try {
      const result = await originalRequest(method, path, data, options);
      const endTime = Date.now();

      const updatedReqs = networkRequests().map((r) =>
        r.id === id
          ? {
              ...r,
              endTime,
              duration: endTime - startTime,
              status: /** @type {'success'} */ ('success'),
              statusCode: 200,
              responseBody: result
            }
          : r
      );
      setNetworkRequests(updatedReqs);

      return result;
    } catch (error) {
      const endTime = Date.now();

      const errorReqs = networkRequests().map((r) =>
        r.id === id
          ? {
              ...r,
              endTime,
              duration: endTime - startTime,
              status: /** @type {'error'} */ ('error'),
              statusCode: /** @type {any} */ (error).status || 0,
              error: /** @type {Error} */ (error).message
            }
          : r
      );
      setNetworkRequests(errorReqs);

      throw error;
    }
  };
}

// =============================================================================
// Action Logger
// =============================================================================

/**
 * Log an action dispatch.
 * @param {string} actionName - Name of the action
 * @param {any} payload - Action payload
 */
export function logAction(actionName, payload) {
  const timestamp = new Date().toISOString().slice(11, 23);
  const entry = `[${timestamp}] ${actionName}: ${JSON.stringify(payload).slice(0, 100)}`;
  const currentLog = actionLog();
  setActionLog([entry, ...currentLog].slice(0, 100)); // Keep last 100
}

// =============================================================================
// UI Rendering
// =============================================================================

/**
 * Create the devtools panel element.
 * @returns {HTMLDivElement}
 */
function createDevToolsPanel() {
  const panel = document.createElement('div');
  panel.id = 'dnr-devtools';
  panel.innerHTML = `
    <style>
      #dnr-devtools {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 300px;
        background: #1e1e1e;
        color: #d4d4d4;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        font-size: 12px;
        z-index: 99999;
        display: none;
        flex-direction: column;
        border-top: 2px solid #007acc;
        box-shadow: 0 -4px 20px rgba(0,0,0,0.3);
      }
      #dnr-devtools.open { display: flex; }
      #dnr-devtools-header {
        display: flex;
        align-items: center;
        background: #252526;
        padding: 4px 8px;
        border-bottom: 1px solid #3c3c3c;
      }
      #dnr-devtools-title {
        font-weight: bold;
        color: #007acc;
        margin-right: 16px;
      }
      #dnr-devtools-tabs {
        display: flex;
        gap: 4px;
        flex: 1;
      }
      .dnr-devtools-tab {
        padding: 4px 12px;
        background: transparent;
        border: none;
        color: #808080;
        cursor: pointer;
        border-radius: 4px;
        transition: all 0.15s;
      }
      .dnr-devtools-tab:hover { color: #d4d4d4; background: #3c3c3c; }
      .dnr-devtools-tab.active { color: #fff; background: #007acc; }
      #dnr-devtools-close {
        background: none;
        border: none;
        color: #808080;
        cursor: pointer;
        font-size: 16px;
        padding: 4px 8px;
      }
      #dnr-devtools-close:hover { color: #fff; }
      #dnr-devtools-content {
        flex: 1;
        overflow: auto;
        padding: 8px;
      }
      .dnr-devtools-section {
        margin-bottom: 12px;
      }
      .dnr-devtools-section-title {
        color: #569cd6;
        margin-bottom: 4px;
        font-weight: bold;
      }
      .dnr-devtools-tree {
        margin-left: 12px;
      }
      .dnr-devtools-key { color: #9cdcfe; }
      .dnr-devtools-string { color: #ce9178; }
      .dnr-devtools-number { color: #b5cea8; }
      .dnr-devtools-boolean { color: #569cd6; }
      .dnr-devtools-null { color: #808080; }
      .dnr-network-row {
        display: flex;
        padding: 4px 8px;
        border-bottom: 1px solid #3c3c3c;
        cursor: pointer;
      }
      .dnr-network-row:hover { background: #2d2d2d; }
      .dnr-network-method {
        width: 60px;
        font-weight: bold;
      }
      .dnr-network-method.GET { color: #4ec9b0; }
      .dnr-network-method.POST { color: #dcdcaa; }
      .dnr-network-method.PUT { color: #c586c0; }
      .dnr-network-method.DELETE { color: #f14c4c; }
      .dnr-network-url { flex: 1; color: #9cdcfe; }
      .dnr-network-status { width: 50px; text-align: center; }
      .dnr-network-status.success { color: #4ec9b0; }
      .dnr-network-status.error { color: #f14c4c; }
      .dnr-network-status.pending { color: #dcdcaa; }
      .dnr-network-time { width: 60px; text-align: right; color: #808080; }
      .dnr-action-row {
        padding: 2px 0;
        font-family: monospace;
      }
      .dnr-devtools-hint {
        color: #808080;
        font-size: 11px;
        padding: 8px 0;
      }
    </style>
    <div id="dnr-devtools-header">
      <span id="dnr-devtools-title">🔧 DNR DevTools</span>
      <div id="dnr-devtools-tabs">
        <button class="dnr-devtools-tab active" data-tab="state">State</button>
        <button class="dnr-devtools-tab" data-tab="network">Network</button>
        <button class="dnr-devtools-tab" data-tab="actions">Actions</button>
      </div>
      <button id="dnr-devtools-close" title="Close (Ctrl+Shift+D)">✕</button>
    </div>
    <div id="dnr-devtools-content"></div>
  `;

  return panel;
}

/**
 * Format a value for display in the state inspector.
 * @param {any} value
 * @param {number} [indent=0]
 * @returns {string}
 */
function formatValue(value, indent = 0) {
  if (value === null) return '<span class="dnr-devtools-null">null</span>';
  if (value === undefined) return '<span class="dnr-devtools-null">undefined</span>';

  const type = typeof value;
  if (type === 'string')
    return `<span class="dnr-devtools-string">"${escapeHtml(value)}"</span>`;
  if (type === 'number')
    return `<span class="dnr-devtools-number">${value}</span>`;
  if (type === 'boolean')
    return `<span class="dnr-devtools-boolean">${value}</span>`;

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    const items = value.slice(0, 10).map((v) => formatValue(v, indent + 1));
    const suffix = value.length > 10 ? ` ... +${value.length - 10} more` : '';
    return `[${items.join(', ')}${suffix}]`;
  }

  if (type === 'object') {
    const keys = Object.keys(value).slice(0, 10);
    if (keys.length === 0) return '{}';
    const entries = keys.map(
      (k) =>
        `<span class="dnr-devtools-key">${escapeHtml(k)}</span>: ${formatValue(value[k], indent + 1)}`
    );
    const suffix =
      Object.keys(value).length > 10
        ? ` ... +${Object.keys(value).length - 10} more`
        : '';
    return `{ ${entries.join(', ')}${suffix} }`;
  }

  return String(value);
}

/**
 * Escape HTML special characters.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Render the state inspector tab.
 * @returns {string}
 */
function renderStateTab() {
  const scopes = ['local', 'workspace', 'app', 'session'];
  let html = '';

  for (const scope of scopes) {
    const store = stateStores[/** @type {keyof typeof stateStores} */ (scope)];
    if (store.size === 0) continue;

    html += `<div class="dnr-devtools-section">
      <div class="dnr-devtools-section-title">${scope}</div>
      <div class="dnr-devtools-tree">`;

    for (const [key, [getter]] of store.entries()) {
      const value = getter();
      html += `<div><span class="dnr-devtools-key">${escapeHtml(key)}</span>: ${formatValue(value)}</div>`;
    }

    html += '</div></div>';
  }

  if (!html) {
    html = '<div class="dnr-devtools-hint">No state registered yet.</div>';
  }

  return html;
}

/**
 * Render the network tab.
 * @returns {string}
 */
function renderNetworkTab() {
  const requests = networkRequests();

  if (requests.length === 0) {
    return '<div class="dnr-devtools-hint">No network requests yet. API calls will appear here.</div>';
  }

  let html = '';
  for (const req of requests) {
    const statusClass = req.status;
    const duration = req.duration ? `${req.duration}ms` : '...';
    const statusCode = req.statusCode || (req.status === 'pending' ? '...' : 'ERR');

    html += `<div class="dnr-network-row">
      <span class="dnr-network-method ${req.method}">${req.method}</span>
      <span class="dnr-network-url">${escapeHtml(req.url)}</span>
      <span class="dnr-network-status ${statusClass}">${statusCode}</span>
      <span class="dnr-network-time">${duration}</span>
    </div>`;
  }

  return html;
}

/**
 * Render the actions tab.
 * @returns {string}
 */
function renderActionsTab() {
  const actions = actionLog();

  if (actions.length === 0) {
    return '<div class="dnr-devtools-hint">No actions dispatched yet. Action dispatches will appear here.</div>';
  }

  return actions
    .map((a) => `<div class="dnr-action-row">${escapeHtml(a)}</div>`)
    .join('');
}

/**
 * Update the content area based on active tab.
 */
function updateContent() {
  const content = document.getElementById('dnr-devtools-content');
  if (!content) return;

  const tab = activeTab();
  switch (tab) {
    case 'state':
      content.innerHTML = renderStateTab();
      break;
    case 'network':
      content.innerHTML = renderNetworkTab();
      break;
    case 'actions':
      content.innerHTML = renderActionsTab();
      break;
  }
}

// =============================================================================
// Initialization
// =============================================================================

let initialized = false;

/**
 * Initialize the DevTools panel.
 * Call this to enable dev tools in development mode.
 */
export function initDevTools() {
  if (initialized) return;
  initialized = true;

  // Intercept network requests
  interceptNetworkRequests();

  // Set up action logging
  setActionLogger(logAction);

  // Create and append panel
  const panel = createDevToolsPanel();
  document.body.appendChild(panel);

  // Set up tab switching
  const tabs = panel.querySelectorAll('.dnr-devtools-tab');
  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      tabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      setActiveTab(/** @type {DevToolsTab} */ (tab.getAttribute('data-tab') || 'state'));
    });
  });

  // Close button
  const closeBtn = document.getElementById('dnr-devtools-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => setIsOpen(false));
  }

  // Keyboard shortcut: Ctrl+Shift+D
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
      e.preventDefault();
      setIsOpen(!isOpen());
    }
  });

  // React to state changes
  createEffect(() => {
    const open = isOpen();
    panel.classList.toggle('open', open);
    if (open) updateContent();
  });

  createEffect(() => {
    activeTab(); // Subscribe to tab changes
    if (isOpen()) updateContent();
  });

  createEffect(() => {
    networkRequests(); // Subscribe to network changes
    if (isOpen() && activeTab() === 'network') updateContent();
  });

  createEffect(() => {
    actionLog(); // Subscribe to action changes
    if (isOpen() && activeTab() === 'actions') updateContent();
  });

  // Auto-refresh state tab periodically when open
  setInterval(() => {
    if (isOpen() && activeTab() === 'state') updateContent();
  }, 1000);

  console.log('[DNR DevTools] Initialized. Press Ctrl+Shift+D to toggle.');
}

/**
 * Toggle DevTools visibility.
 */
export function toggleDevTools() {
  setIsOpen(!isOpen());
}

/**
 * Open DevTools.
 */
export function openDevTools() {
  setIsOpen(true);
}

/**
 * Close DevTools.
 */
export function closeDevTools() {
  setIsOpen(false);
}

// Export state for external access
export { isOpen, networkRequests, actionLog };
