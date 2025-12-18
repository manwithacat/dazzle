// @ts-check
/**
 * Email Panel - Shows recent outbox messages in the Dazzle Bar
 * Part of the Dazzle Native Runtime
 *
 * Displays email messages sent through the messaging system with
 * links to Mailpit for viewing in development.
 *
 * @module dazzle-bar/email-panel
 */

import { createSignal, createEffect } from '../signals.js';

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @typedef {Object} OutboxMessage
 * @property {string} id - Message ID
 * @property {string} channel - Channel name
 * @property {string} recipient - Email recipient
 * @property {string} subject - Email subject
 * @property {'pending'|'processing'|'sent'|'failed'|'dead_letter'} status - Message status
 * @property {string} created_at - ISO timestamp
 * @property {string|null} last_error - Last error message
 */

/**
 * @typedef {Object} OutboxStats
 * @property {number} [pending] - Pending message count
 * @property {number} [processing] - Processing message count
 * @property {number} [sent] - Sent message count
 * @property {number} [failed] - Failed message count
 * @property {number} [dead_letter] - Dead letter message count
 */

/**
 * @typedef {Object} EmailPanelState
 * @property {OutboxMessage[]} messages - Recent messages
 * @property {OutboxStats} stats - Message statistics
 * @property {string|null} mailpitUrl - Mailpit management URL
 * @property {boolean} isOpen - Whether panel is open
 * @property {boolean} isLoading - Whether data is loading
 * @property {string|null} error - Error message
 */

// =============================================================================
// State
// =============================================================================

/** @type {import('../signals.js').Signal<OutboxMessage[]>} */
const [messages, setMessages] = createSignal(/** @type {OutboxMessage[]} */ ([]));

/** @type {import('../signals.js').Signal<OutboxStats>} */
const [stats, setStats] = createSignal(/** @type {OutboxStats} */ ({}));

/** @type {import('../signals.js').Signal<string|null>} */
const [mailpitUrl, setMailpitUrl] = createSignal(/** @type {string|null} */ (null));

/** @type {import('../signals.js').Signal<boolean>} */
const [isPanelOpen, setIsPanelOpen] = createSignal(false);

/** @type {import('../signals.js').Signal<boolean>} */
const [emailIsLoading, setEmailIsLoading] = createSignal(false);

/** @type {import('../signals.js').Signal<string|null>} */
const [panelError, setPanelError] = createSignal(/** @type {string|null} */ (null));

// =============================================================================
// API Functions
// =============================================================================

/**
 * Fetch recent outbox messages.
 * @param {number} [limit=20] - Maximum messages to fetch
 * @returns {Promise<{messages: OutboxMessage[], stats: OutboxStats}>}
 */
async function fetchRecentMessages(limit = 20) {
  const response = await fetch(`/_dazzle/channels/outbox/recent?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch messages: ${response.status}`);
  }
  return response.json();
}

/**
 * Fetch channel status to get Mailpit URL.
 * @returns {Promise<{channels: Array<{name: string, management_url: string|null}>}>}
 */
async function fetchChannelStatus() {
  const response = await fetch('/_dazzle/channels/');
  if (!response.ok) {
    throw new Error(`Failed to fetch channel status: ${response.status}`);
  }
  return response.json();
}

/**
 * Refresh email panel data.
 */
async function refreshEmailData() {
  setEmailIsLoading(true);
  setPanelError(null);

  try {
    // Fetch messages and channel status in parallel
    const [messagesData, channelsData] = await Promise.all([
      fetchRecentMessages(),
      fetchChannelStatus()
    ]);

    setMessages(messagesData.messages || []);
    setStats(messagesData.stats || {});

    // Find Mailpit URL from channels
    const emailChannel = channelsData.channels?.find(
      (ch) => ch.management_url && ch.management_url.includes('8025')
    );
    if (emailChannel?.management_url) {
      setMailpitUrl(emailChannel.management_url);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to fetch email data';
    setPanelError(message);
    console.error('[Email Panel] Error:', err);
  } finally {
    setEmailIsLoading(false);
  }
}

// =============================================================================
// Styles
// =============================================================================

const panelStyles = `
  .dazzle-email-panel {
    position: fixed;
    top: 48px;
    right: 120px;
    width: 380px;
    max-height: 480px;
    background: #1a1a2e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    z-index: 9999998;
    display: none;
    flex-direction: column;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    color: #e8e8e8;
  }

  .dazzle-email-panel.open {
    display: flex;
  }

  .dazzle-email-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid #0f3460;
  }

  .dazzle-email-panel-title {
    font-weight: 600;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .dazzle-email-panel-stats {
    display: flex;
    gap: 12px;
    font-size: 11px;
    color: #888;
  }

  .dazzle-email-stat {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .dazzle-email-stat-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .dazzle-email-stat-dot.sent { background: #4ade80; }
  .dazzle-email-stat-dot.pending { background: #fbbf24; }
  .dazzle-email-stat-dot.failed { background: #ef4444; }

  .dazzle-email-panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .dazzle-email-empty {
    padding: 32px 16px;
    text-align: center;
    color: #666;
  }

  .dazzle-email-empty-icon {
    font-size: 32px;
    margin-bottom: 8px;
    opacity: 0.5;
  }

  .dazzle-email-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }

  .dazzle-email-item:hover {
    background: #0f3460;
  }

  .dazzle-email-status {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
  }

  .dazzle-email-status.sent { background: #4ade80; }
  .dazzle-email-status.pending { background: #fbbf24; }
  .dazzle-email-status.processing { background: #fbbf24; animation: dazzle-pulse 1s ease-in-out infinite; }
  .dazzle-email-status.failed { background: #ef4444; }
  .dazzle-email-status.dead_letter { background: #ef4444; }

  .dazzle-email-content {
    flex: 1;
    min-width: 0;
  }

  .dazzle-email-subject {
    font-weight: 500;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .dazzle-email-meta {
    font-size: 11px;
    color: #888;
    display: flex;
    gap: 8px;
  }

  .dazzle-email-recipient {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 180px;
  }

  .dazzle-email-time {
    flex-shrink: 0;
  }

  .dazzle-email-error {
    font-size: 11px;
    color: #ef4444;
    margin-top: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .dazzle-email-panel-footer {
    padding: 12px 16px;
    border-top: 1px solid #0f3460;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .dazzle-email-refresh-btn {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 12px;
    transition: color 0.15s;
  }

  .dazzle-email-refresh-btn:hover {
    color: #e8e8e8;
  }

  .dazzle-email-refresh-btn.loading {
    animation: dazzle-spin 1s linear infinite;
  }

  .dazzle-mailpit-link {
    color: #e94560;
    text-decoration: none;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .dazzle-mailpit-link:hover {
    text-decoration: underline;
  }

  @keyframes dazzle-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  @keyframes dazzle-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* Responsive */
  @media (max-width: 540px) {
    .dazzle-email-panel {
      right: 8px;
      left: 8px;
      width: auto;
    }
  }
`;

// =============================================================================
// Panel Rendering
// =============================================================================

/**
 * Format a relative time string.
 * @param {string} isoString - ISO timestamp
 * @returns {string} - Relative time string
 */
function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

/**
 * Create the email panel element.
 * @returns {HTMLDivElement}
 */
function createEmailPanel() {
  const panel = document.createElement('div');
  panel.className = 'dazzle-email-panel';
  panel.id = 'dazzle-email-panel';
  panel.setAttribute('data-dazzle-component', 'email-panel');

  updatePanelContent(panel);
  return panel;
}

/**
 * Update the panel content.
 * @param {HTMLDivElement} panel - Panel element
 */
function updatePanelContent(panel) {
  const msgList = messages();
  const statsData = stats();
  const mailpit = mailpitUrl();
  const loading = emailIsLoading();
  const err = panelError();

  const sentCount = statsData.sent || 0;
  const pendingCount = (statsData.pending || 0) + (statsData.processing || 0);
  const failedCount = (statsData.failed || 0) + (statsData.dead_letter || 0);

  panel.innerHTML = `
    <div class="dazzle-email-panel-header">
      <div class="dazzle-email-panel-title">
        <span>&#x2709;</span>
        Email Outbox
      </div>
      <div class="dazzle-email-panel-stats">
        <span class="dazzle-email-stat">
          <span class="dazzle-email-stat-dot sent"></span>
          ${sentCount}
        </span>
        <span class="dazzle-email-stat">
          <span class="dazzle-email-stat-dot pending"></span>
          ${pendingCount}
        </span>
        <span class="dazzle-email-stat">
          <span class="dazzle-email-stat-dot failed"></span>
          ${failedCount}
        </span>
      </div>
    </div>
    <div class="dazzle-email-panel-body">
      ${err ? `<div class="dazzle-email-empty"><div class="dazzle-email-empty-icon">&#x26A0;</div>${err}</div>` : ''}
      ${!err && msgList.length === 0 ? `
        <div class="dazzle-email-empty">
          <div class="dazzle-email-empty-icon">&#x2709;</div>
          No emails sent yet
        </div>
      ` : ''}
      ${msgList.map((msg) => `
        <div class="dazzle-email-item" data-message-id="${msg.id}" title="${msg.status}">
          <span class="dazzle-email-status ${msg.status}"></span>
          <div class="dazzle-email-content">
            <div class="dazzle-email-subject">${escapeHtml(msg.subject)}</div>
            <div class="dazzle-email-meta">
              <span class="dazzle-email-recipient">${escapeHtml(msg.recipient)}</span>
              <span class="dazzle-email-time">${formatRelativeTime(msg.created_at)}</span>
            </div>
            ${msg.last_error ? `<div class="dazzle-email-error" title="${escapeHtml(msg.last_error)}">${escapeHtml(msg.last_error)}</div>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
    <div class="dazzle-email-panel-footer">
      <button class="dazzle-email-refresh-btn ${loading ? 'loading' : ''}" id="dazzle-email-refresh">
        &#x21bb; Refresh
      </button>
      ${mailpit ? `
        <a href="${mailpit}" target="_blank" class="dazzle-mailpit-link">
          Open Mailpit &#x2197;
        </a>
      ` : ''}
    </div>
  `;

  // Add refresh button handler
  const refreshBtn = panel.querySelector('#dazzle-email-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => refreshEmailData());
  }
}

/**
 * Escape HTML special characters.
 * @param {string} str - String to escape
 * @returns {string} - Escaped string
 */
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Inject panel styles into the document.
 */
function injectPanelStyles() {
  if (document.getElementById('dazzle-email-panel-styles')) return;

  const style = document.createElement('style');
  style.id = 'dazzle-email-panel-styles';
  style.textContent = panelStyles;
  document.head.appendChild(style);
}

// =============================================================================
// Panel Management
// =============================================================================

/** @type {HTMLDivElement|null} */
let panelElement = null;

/**
 * Toggle the email panel visibility.
 */
function toggleEmailPanel() {
  setIsPanelOpen(!isPanelOpen());
}

/**
 * Open the email panel.
 */
function openEmailPanel() {
  setIsPanelOpen(true);
}

/**
 * Close the email panel.
 */
function closeEmailPanel() {
  setIsPanelOpen(false);
}

/**
 * Initialize the email panel.
 * Called by the main bar initialization.
 */
function initEmailPanel() {
  injectPanelStyles();

  // Create panel element
  panelElement = createEmailPanel();
  document.body.appendChild(panelElement);

  // Set up reactive updates
  createEffect(() => {
    const open = isPanelOpen();
    if (panelElement) {
      panelElement.classList.toggle('open', open);
      if (open) {
        refreshEmailData();
      }
    }
  });

  createEffect(() => {
    // Trigger update when data changes
    messages();
    stats();
    mailpitUrl();
    emailIsLoading();
    panelError();

    if (panelElement) {
      updatePanelContent(panelElement);
    }
  });

  // Close panel when clicking outside
  document.addEventListener('click', (e) => {
    const target = /** @type {HTMLElement} */ (e.target);
    if (
      isPanelOpen() &&
      panelElement &&
      !panelElement.contains(target) &&
      !target.closest('#dazzle-email-btn')
    ) {
      closeEmailPanel();
    }
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isPanelOpen()) {
      closeEmailPanel();
    }
  });
}

// =============================================================================
// Exports
// =============================================================================

export {
  initEmailPanel,
  toggleEmailPanel,
  openEmailPanel,
  closeEmailPanel,
  refreshEmailData,
  isPanelOpen,
  messages,
  stats,
  mailpitUrl
};
