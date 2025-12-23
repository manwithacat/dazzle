/**
 * Dazzle Control Plane Application
 *
 * Client-side application for the ops dashboard.
 * Connects to /_ops/ API endpoints and SSE streams.
 */

// @ts-check
'use strict';

/* ==========================================================================
   State
   ========================================================================== */

/** @type {EventSource | null} */
let healthSSE = null;

/** @type {EventSource | null} */
let eventsSSE = null;

/** @type {string | null} */
let currentPanel = 'health';

/* ==========================================================================
   API Helpers
   ========================================================================== */

/**
 * Make API request to ops endpoints
 * @param {string} path - API path (relative to /_ops/)
 * @param {RequestInit} [options] - Fetch options
 * @returns {Promise<any>}
 */
async function api(path, options = {}) {
    const response = await fetch(`/_ops${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        credentials: 'include', // Include cookies for auth
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

/* ==========================================================================
   Authentication
   ========================================================================== */

/**
 * Check if setup is required
 */
async function checkSetup() {
    try {
        const { setup_required } = await api('/setup-required');

        if (setup_required) {
            showElement('setup-form');
            hideElement('login-form');
        } else {
            // Try to get current user (check if already logged in)
            try {
                await api('/me');
                showDashboard();
            } catch {
                showElement('login-form');
                hideElement('setup-form');
            }
        }
    } catch (error) {
        console.error('Setup check failed:', error);
        showElement('login-form');
    }
}

/**
 * Handle initial setup form submission
 * @param {Event} event
 */
async function handleSetup(event) {
    event.preventDefault();

    const username = /** @type {HTMLInputElement} */ (
        document.getElementById('setup-username')
    ).value;
    const password = /** @type {HTMLInputElement} */ (
        document.getElementById('setup-password')
    ).value;
    const confirm = /** @type {HTMLInputElement} */ (
        document.getElementById('setup-password-confirm')
    ).value;

    const errorEl = document.getElementById('setup-error');

    if (password !== confirm) {
        if (errorEl) errorEl.textContent = 'Passwords do not match';
        return;
    }

    try {
        await api('/setup', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        showDashboard();
    } catch (error) {
        if (errorEl) errorEl.textContent = error instanceof Error ? error.message : 'Setup failed';
    }
}

/**
 * Handle login form submission
 * @param {Event} event
 */
async function handleLogin(event) {
    event.preventDefault();

    const username = /** @type {HTMLInputElement} */ (
        document.getElementById('login-username')
    ).value;
    const password = /** @type {HTMLInputElement} */ (
        document.getElementById('login-password')
    ).value;

    const errorEl = document.getElementById('login-error');

    try {
        await api('/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        showDashboard();
    } catch (error) {
        if (errorEl) errorEl.textContent = error instanceof Error ? error.message : 'Login failed';
    }
}

/**
 * Handle logout
 */
async function handleLogout() {
    try {
        await api('/logout', { method: 'POST' });
    } catch {
        // Ignore errors
    }

    disconnectSSE();
    hideElement('dashboard-screen');
    showElement('login-screen');
    showElement('login-form');
    hideElement('setup-form');
}

/* ==========================================================================
   Dashboard
   ========================================================================== */

/**
 * Show the dashboard
 */
function showDashboard() {
    hideElement('login-screen');
    showElement('dashboard-screen');

    // Set up navigation
    setupNavigation();

    // Load initial data
    refreshHealth();
    loadRetentionConfig();

    // Connect to SSE
    connectHealthSSE();
}

/**
 * Set up navigation click handlers
 */
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const panel = item.getAttribute('data-panel');
            if (panel) {
                switchPanel(panel);
            }
        });
    });
}

/**
 * Switch to a different panel
 * @param {string} panelId
 */
function switchPanel(panelId) {
    currentPanel = panelId;

    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.getAttribute('data-panel') === panelId);
    });

    // Update panels
    document.querySelectorAll('.panel').forEach(panel => {
        panel.classList.toggle('hidden', panel.id !== `${panelId}-panel`);
    });

    // Load panel-specific data
    switch (panelId) {
        case 'events':
            loadEvents();
            break;
        case 'api-calls':
            loadApiStats();
            break;
        case 'analytics':
            loadAnalyticsTenants();
            break;
        case 'emails':
            loadEmailStats();
            break;
        case 'settings':
            loadRetentionConfig();
            loadSSEStats();
            loadSimulationStatus();
            break;
    }
}

/* ==========================================================================
   Health Panel
   ========================================================================== */

/**
 * Refresh health data
 */
async function refreshHealth() {
    try {
        const health = await api('/health');
        renderHealth(health);
    } catch (error) {
        console.error('Failed to load health:', error);
    }
}

/**
 * Render health data
 * @param {Object} health
 */
function renderHealth(health) {
    // Update status badge
    const badge = document.getElementById('health-status-badge');
    if (badge) {
        badge.textContent = health.status.replace('_', ' ');
        badge.className = 'status-badge ' + getStatusClass(health.status);
    }

    // Update summary
    const summary = health.summary || {};
    setTextContent('healthy-count', summary.healthy || 0);
    setTextContent('degraded-count', summary.degraded || 0);
    setTextContent('unhealthy-count', summary.unhealthy || 0);

    // Render components
    const container = document.getElementById('health-components');
    if (!container) return;

    if (!health.components || health.components.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No components registered</p>';
        return;
    }

    container.innerHTML = health.components.map(renderComponentCard).join('');
}

/**
 * Render a component health card
 * @param {Object} component
 * @returns {string}
 */
function renderComponentCard(component) {
    const statusClass = component.status.toLowerCase();
    const latency = component.latency_ms ? `${Math.round(component.latency_ms)}ms` : '-';

    return `
        <div class="component-card">
            <div class="component-card-header">
                <span class="component-name">${escapeHtml(component.name)}</span>
                <span class="component-type">${escapeHtml(component.type)}</span>
            </div>
            <div class="component-status">
                <span class="status-dot ${statusClass}"></span>
                <span class="component-message">${escapeHtml(component.message || component.status)}</span>
            </div>
            <div class="component-latency">Latency: ${latency}</div>
        </div>
    `;
}

/**
 * Connect to health SSE stream
 */
function connectHealthSSE() {
    if (healthSSE) {
        healthSSE.close();
    }

    healthSSE = new EventSource('/_ops/sse/health');

    healthSSE.onopen = () => {
        updateSSEStatus(true);
    };

    healthSSE.onerror = () => {
        updateSSEStatus(false);
        // Reconnect after delay
        setTimeout(connectHealthSSE, 5000);
    };

    healthSSE.addEventListener('ops.health.updated', (event) => {
        try {
            const health = JSON.parse(event.data);
            renderHealth(health);
        } catch (e) {
            console.error('Failed to parse health event:', e);
        }
    });

    healthSSE.addEventListener('heartbeat', () => {
        // Keep-alive received
    });
}

/**
 * Update SSE connection status indicator
 * @param {boolean} connected
 */
function updateSSEStatus(connected) {
    const indicator = document.getElementById('sse-indicator');
    const label = document.getElementById('sse-label');

    if (indicator) {
        indicator.className = 'sse-indicator ' + (connected ? 'connected' : 'disconnected');
    }
    if (label) {
        label.textContent = connected ? 'Live updates connected' : 'Reconnecting...';
    }
}

/**
 * Disconnect all SSE streams
 */
function disconnectSSE() {
    if (healthSSE) {
        healthSSE.close();
        healthSSE = null;
    }
    if (eventsSSE) {
        eventsSSE.close();
        eventsSSE = null;
    }
}

/* ==========================================================================
   Events Panel
   ========================================================================== */

/**
 * Load events
 */
async function loadEvents() {
    try {
        const entityFilter = /** @type {HTMLSelectElement} */ (
            document.getElementById('event-entity-filter')
        )?.value;
        const typeFilter = /** @type {HTMLSelectElement} */ (
            document.getElementById('event-type-filter')
        )?.value;
        const tenantFilter = /** @type {HTMLInputElement} */ (
            document.getElementById('event-tenant-filter')
        )?.value;

        let query = '?limit=50';
        if (entityFilter) query += `&entity_name=${encodeURIComponent(entityFilter)}`;
        if (typeFilter) query += `&event_type=${encodeURIComponent(typeFilter)}`;
        if (tenantFilter) query += `&tenant_id=${encodeURIComponent(tenantFilter)}`;

        const result = await api(`/events${query}`);
        renderEvents(result.events);
    } catch (error) {
        console.error('Failed to load events:', error);
    }
}

/**
 * Render events list
 * @param {Array} events
 */
function renderEvents(events) {
    const container = document.getElementById('event-list');
    if (!container) return;

    if (!events || events.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No events found</p>';
        return;
    }

    container.innerHTML = events.map(renderEventItem).join('');
}

/**
 * Render a single event item
 * @param {Object} event
 * @returns {string}
 */
function renderEventItem(event) {
    const action = event.event_type.split('.').pop() || 'unknown';
    const time = new Date(event.recorded_at).toLocaleString();

    return `
        <div class="event-item">
            <span class="event-type ${action}">${escapeHtml(action)}</span>
            <span class="event-entity">
                <span class="event-entity-name">${escapeHtml(event.entity_name || '-')}</span>
                <span class="event-entity-id">${escapeHtml(event.entity_id || '')}</span>
            </span>
            <span class="event-time">${time}</span>
        </div>
    `;
}

/* ==========================================================================
   API Calls Panel (Integration Observatory)
   ========================================================================== */

/**
 * Load API call statistics and related data
 */
async function loadApiStats() {
    try {
        const hours = /** @type {HTMLSelectElement} */ (
            document.getElementById('api-hours-filter')
        )?.value || '24';

        // Load stats, costs, and errors in parallel
        const [stats, costs, errors] = await Promise.all([
            api(`/api-calls/stats?hours=${hours}`),
            api('/api-calls/costs?days=30'),
            api(`/api-calls/errors?hours=${hours}`),
        ]);

        renderApiStats(stats, costs, errors);
    } catch (error) {
        console.error('Failed to load API stats:', error);
        const container = document.getElementById('api-stats');
        if (container) {
            container.innerHTML = '<p class="placeholder-text">Failed to load API data</p>';
        }
    }
}

/**
 * Render API statistics with costs and errors
 * @param {Object} stats
 * @param {Object} costs
 * @param {Object} errors
 */
function renderApiStats(stats, costs, errors) {
    const container = document.getElementById('api-stats');
    if (!container) return;

    const services = stats.services || {};

    // Build cost summary section
    const costHtml = `
        <div class="api-cost-summary">
            <h3>Monthly Cost Summary</h3>
            <div class="cost-total">
                <span class="cost-value">£${costs.total_cost_gbp || '0.00'}</span>
                <span class="cost-label">Last 30 days</span>
            </div>
            <div class="cost-breakdown">
                ${(costs.breakdown || []).slice(0, 5).map(item => `
                    <div class="cost-item">
                        <span class="cost-service">${escapeHtml(item.service_name)}</span>
                        <span class="cost-amount">£${((item.total_cost_cents || 0) / 100).toFixed(2)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // Build errors section
    const errorsHtml = errors.total_errors > 0 ? `
        <div class="api-errors-summary">
            <h3>Recent Errors (${errors.period_hours}h)</h3>
            <div class="error-count ${errors.total_errors > 10 ? 'high' : ''}">
                ${errors.total_errors} errors
            </div>
            <div class="error-list">
                ${(errors.recent_errors || []).slice(0, 5).map(err => `
                    <div class="error-item">
                        <span class="error-service">${escapeHtml(err.service_name)}</span>
                        <span class="error-code">${err.status_code || 'timeout'}</span>
                        <span class="error-endpoint">${escapeHtml(err.endpoint)}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    ` : '';

    // Build services section
    let servicesHtml = '';
    if (Object.keys(services).length === 0) {
        servicesHtml = '<p class="placeholder-text">No API calls recorded</p>';
    } else {
        servicesHtml = `
            <div class="api-services-grid">
                ${Object.entries(services).map(([name, data]) =>
                    renderApiServiceCard(name, /** @type {Object} */ (data))
                ).join('')}
            </div>
        `;
    }

    container.innerHTML = `
        <div class="api-dashboard">
            <div class="api-top-row">
                ${costHtml}
                ${errorsHtml}
            </div>
            <h3>Services</h3>
            ${servicesHtml}
        </div>
    `;
}

/**
 * Render API service card
 * @param {string} name
 * @param {Object} stats
 * @returns {string}
 */
function renderApiServiceCard(name, stats) {
    const errorClass = stats.error_rate > 10 ? 'unhealthy' : stats.error_rate > 5 ? 'degraded' : 'healthy';
    const latencyClass = stats.avg_latency_ms > 1000 ? 'slow' : stats.avg_latency_ms > 500 ? 'moderate' : 'fast';

    return `
        <div class="api-service-card">
            <div class="api-service-header">
                <span class="api-service-name">${escapeHtml(name)}</span>
                <span class="status-badge ${errorClass}">
                    ${stats.error_rate}% errors
                </span>
            </div>
            <div class="api-service-stats">
                <div class="api-stat">
                    <span class="api-stat-value">${stats.total_calls}</span>
                    <span class="api-stat-label">Calls</span>
                </div>
                <div class="api-stat ${latencyClass}">
                    <span class="api-stat-value">${Math.round(stats.avg_latency_ms)}ms</span>
                    <span class="api-stat-label">Avg Latency</span>
                </div>
                <div class="api-stat">
                    <span class="api-stat-value">${stats.error_count}</span>
                    <span class="api-stat-label">Errors</span>
                </div>
                <div class="api-stat">
                    <span class="api-stat-value">£${((stats.total_cost_cents || 0) / 100).toFixed(2)}</span>
                    <span class="api-stat-label">Cost</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Load recent API calls for detail view
 */
async function loadRecentApiCalls() {
    try {
        const result = await api('/api-calls/recent?limit=20');
        console.log('Recent API calls:', result);
        // Could render in a modal or detail panel
    } catch (error) {
        console.error('Failed to load recent calls:', error);
    }
}

/* ==========================================================================
   Analytics Panel
   ========================================================================== */

/** @type {string | null} */
let selectedTenantId = null;

/**
 * Load available tenants for analytics
 */
async function loadAnalyticsTenants() {
    try {
        const result = await api('/analytics/tenants');
        const select = /** @type {HTMLSelectElement} */ (
            document.getElementById('analytics-tenant-filter')
        );

        if (!select) return;

        // Clear existing options except first
        while (select.options.length > 1) {
            select.remove(1);
        }

        // Add tenant options
        for (const tenant of result.tenants || []) {
            const option = document.createElement('option');
            option.value = tenant.tenant_id;
            option.textContent = `${tenant.tenant_id} (${tenant.event_count} events)`;
            select.appendChild(option);
        }

        // If a tenant is selected, load its data
        if (selectedTenantId) {
            select.value = selectedTenantId;
            await loadAnalyticsData(selectedTenantId);
        }
    } catch (error) {
        console.error('Failed to load analytics tenants:', error);
    }
}

/**
 * Handle tenant selection change
 * @param {Event} event
 */
async function onTenantChange(event) {
    const select = /** @type {HTMLSelectElement} */ (event.target);
    selectedTenantId = select.value || null;

    if (selectedTenantId) {
        await loadAnalyticsData(selectedTenantId);
    } else {
        const content = document.getElementById('analytics-content');
        if (content) {
            content.innerHTML = '<p class="placeholder-text">Select a tenant to view analytics</p>';
        }
    }
}

/**
 * Load analytics data for a tenant
 * @param {string} tenantId
 */
async function loadAnalyticsData(tenantId) {
    try {
        const days = /** @type {HTMLSelectElement} */ (
            document.getElementById('analytics-days-filter')
        )?.value || '7';

        const [summary, pageViews, sources] = await Promise.all([
            api(`/analytics/${tenantId}?days=${days}`),
            api(`/analytics/${tenantId}/page-views?days=${days}`),
            api(`/analytics/${tenantId}/traffic-sources?days=${days}`),
        ]);

        renderAnalyticsDashboard(summary, pageViews, sources);
    } catch (error) {
        console.error('Failed to load analytics:', error);
        const content = document.getElementById('analytics-content');
        if (content) {
            content.innerHTML = '<p class="placeholder-text">Failed to load analytics data</p>';
        }
    }
}

/**
 * Render the analytics dashboard
 * @param {Object} summary
 * @param {Object} pageViews
 * @param {Object} sources
 */
function renderAnalyticsDashboard(summary, pageViews, sources) {
    const content = document.getElementById('analytics-content');
    if (!content) return;

    const sessionStats = pageViews.session_stats || {};
    const dailyViews = pageViews.daily_views || [];
    const topPages = pageViews.top_pages || [];
    const trafficSources = sources.sources || [];

    // Calculate totals
    const totalViews = dailyViews.reduce((sum, d) => sum + (d.views || 0), 0);
    const totalSessions = sessionStats.total_sessions || 0;
    const avgViewsPerSession = sessionStats.avg_views_per_session || 0;

    content.innerHTML = `
        <div class="analytics-dashboard">
            <!-- Summary Cards -->
            <div class="analytics-summary">
                <div class="analytics-stat-card">
                    <span class="stat-value">${totalViews.toLocaleString()}</span>
                    <span class="stat-label">Page Views</span>
                </div>
                <div class="analytics-stat-card">
                    <span class="stat-value">${totalSessions.toLocaleString()}</span>
                    <span class="stat-label">Sessions</span>
                </div>
                <div class="analytics-stat-card">
                    <span class="stat-value">${avgViewsPerSession.toFixed(1)}</span>
                    <span class="stat-label">Avg Views/Session</span>
                </div>
            </div>

            <!-- Daily Chart (ASCII-style bar chart) -->
            <div class="analytics-section">
                <h3>Page Views (${pageViews.period_days} days)</h3>
                <div class="daily-chart">
                    ${renderDailyChart(dailyViews)}
                </div>
            </div>

            <div class="analytics-columns">
                <!-- Top Pages -->
                <div class="analytics-section">
                    <h3>Top Pages</h3>
                    <div class="top-pages-list">
                        ${topPages.map((p, i) => `
                            <div class="top-page-item">
                                <span class="page-rank">${i + 1}</span>
                                <span class="page-path">${escapeHtml(p.page || 'unknown')}</span>
                                <span class="page-views">${p.views}</span>
                            </div>
                        `).join('') || '<p class="placeholder-text">No data</p>'}
                    </div>
                </div>

                <!-- Traffic Sources -->
                <div class="analytics-section">
                    <h3>Traffic Sources</h3>
                    <div class="traffic-sources-list">
                        ${renderTrafficSources(trafficSources, totalViews)}
                    </div>
                </div>
            </div>
        </div>
    `;
}

/**
 * Render daily chart as bars
 * @param {Array} dailyViews
 * @returns {string}
 */
function renderDailyChart(dailyViews) {
    if (!dailyViews || dailyViews.length === 0) {
        return '<p class="placeholder-text">No data available</p>';
    }

    // Reverse to show oldest first
    const sorted = [...dailyViews].reverse();
    const maxViews = Math.max(...sorted.map(d => d.views || 0), 1);

    return `
        <div class="chart-bars">
            ${sorted.map(d => {
                const height = Math.max(4, (d.views / maxViews) * 100);
                const date = new Date(d.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
                return `
                    <div class="chart-bar-container" title="${date}: ${d.views} views, ${d.sessions} sessions">
                        <div class="chart-bar" style="height: ${height}%"></div>
                        <span class="chart-label">${date}</span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

/**
 * Render traffic sources with percentages
 * @param {Array} sources
 * @param {number} total
 * @returns {string}
 */
function renderTrafficSources(sources, total) {
    if (!sources || sources.length === 0) {
        return '<p class="placeholder-text">No data</p>';
    }

    return sources.map(s => {
        const pct = total > 0 ? ((s.views / total) * 100).toFixed(1) : '0';
        return `
            <div class="source-item">
                <span class="source-name">${escapeHtml(s.source)}</span>
                <div class="source-bar-container">
                    <div class="source-bar" style="width: ${pct}%"></div>
                </div>
                <span class="source-pct">${pct}%</span>
            </div>
        `;
    }).join('');
}

/* ==========================================================================
   Email Panel
   ========================================================================== */

/**
 * Load email statistics
 */
async function loadEmailStats() {
    try {
        const days = /** @type {HTMLSelectElement} */ (
            document.getElementById('email-days-filter')
        )?.value || '7';

        const [stats, topLinks] = await Promise.all([
            api(`/email/stats?days=${days}`),
            api(`/email/top-links?days=${days}`),
        ]);

        renderEmailDashboard(stats, topLinks);
    } catch (error) {
        console.error('Failed to load email stats:', error);
        const content = document.getElementById('email-content');
        if (content) {
            content.innerHTML = '<p class="placeholder-text">Failed to load email data</p>';
        }
    }
}

/**
 * Render the email dashboard
 * @param {Object} stats
 * @param {Object} topLinks
 */
function renderEmailDashboard(stats, topLinks) {
    const content = document.getElementById('email-content');
    if (!content) return;

    const totals = stats.totals || {};
    const rates = stats.rates || {};
    const daily = stats.daily || [];
    const links = topLinks.links || [];

    content.innerHTML = `
        <div class="email-dashboard">
            <!-- Summary Cards -->
            <div class="email-summary">
                <div class="email-stat-card">
                    <span class="stat-value">${(totals.sent || 0).toLocaleString()}</span>
                    <span class="stat-label">Emails Sent</span>
                </div>
                <div class="email-stat-card">
                    <span class="stat-value">${(totals.opened || 0).toLocaleString()}</span>
                    <span class="stat-label">Opens</span>
                    <span class="stat-rate ${rates.open_rate > 20 ? 'good' : rates.open_rate > 10 ? 'average' : 'poor'}">
                        ${rates.open_rate}%
                    </span>
                </div>
                <div class="email-stat-card">
                    <span class="stat-value">${(totals.clicked || 0).toLocaleString()}</span>
                    <span class="stat-label">Clicks</span>
                    <span class="stat-rate ${rates.click_rate > 5 ? 'good' : rates.click_rate > 2 ? 'average' : 'poor'}">
                        ${rates.click_rate}%
                    </span>
                </div>
            </div>

            <!-- Daily Chart -->
            <div class="email-section">
                <h3>Daily Activity (${stats.period_days} days)</h3>
                <div class="email-chart">
                    ${renderEmailChart(daily)}
                </div>
            </div>

            <!-- Top Links -->
            <div class="email-section">
                <h3>Top Clicked Links</h3>
                <div class="email-links-list">
                    ${renderTopLinks(links)}
                </div>
            </div>
        </div>
    `;
}

/**
 * Render email daily chart
 * @param {Array} daily
 * @returns {string}
 */
function renderEmailChart(daily) {
    if (!daily || daily.length === 0) {
        return '<p class="placeholder-text">No email data available</p>';
    }

    // Reverse to show oldest first
    const sorted = [...daily].reverse();
    const maxValue = Math.max(...sorted.map(d => Math.max(d.sent || 0, d.opened || 0, d.clicked || 0)), 1);

    return `
        <div class="email-chart-container">
            <div class="email-chart-legend">
                <span class="legend-item sent">Sent</span>
                <span class="legend-item opened">Opened</span>
                <span class="legend-item clicked">Clicked</span>
            </div>
            <div class="email-chart-bars">
                ${sorted.map(d => {
                    const date = new Date(d.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
                    const sentHeight = Math.max(4, (d.sent / maxValue) * 100);
                    const openedHeight = Math.max(4, (d.opened / maxValue) * 100);
                    const clickedHeight = Math.max(4, (d.clicked / maxValue) * 100);
                    return `
                        <div class="email-bar-group" title="${date}: ${d.sent} sent, ${d.opened} opened, ${d.clicked} clicked">
                            <div class="email-bars">
                                <div class="email-bar sent" style="height: ${sentHeight}%"></div>
                                <div class="email-bar opened" style="height: ${openedHeight}%"></div>
                                <div class="email-bar clicked" style="height: ${clickedHeight}%"></div>
                            </div>
                            <span class="email-bar-label">${date}</span>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

/**
 * Render top clicked links
 * @param {Array} links
 * @returns {string}
 */
function renderTopLinks(links) {
    if (!links || links.length === 0) {
        return '<p class="placeholder-text">No link clicks recorded</p>';
    }

    const maxClicks = Math.max(...links.map(l => l.clicks), 1);

    return links.map((link, i) => {
        const pct = (link.clicks / maxClicks) * 100;
        const displayUrl = link.url.length > 50 ? link.url.substring(0, 47) + '...' : link.url;
        return `
            <div class="email-link-item">
                <span class="link-rank">${i + 1}</span>
                <span class="link-url" title="${escapeHtml(link.url)}">${escapeHtml(displayUrl)}</span>
                <div class="link-bar-container">
                    <div class="link-bar" style="width: ${pct}%"></div>
                </div>
                <span class="link-clicks">${link.clicks}</span>
            </div>
        `;
    }).join('');
}

/* ==========================================================================
   Settings Panel
   ========================================================================== */

/**
 * Load retention configuration
 */
async function loadRetentionConfig() {
    try {
        const config = await api('/config/retention');

        setInputValue('retention-health', config.health_checks_days);
        setInputValue('retention-api', config.api_calls_days);
        setInputValue('retention-events', config.events_days);
        setInputValue('retention-analytics', config.analytics_days);
    } catch (error) {
        console.error('Failed to load retention config:', error);
    }
}

/**
 * Save retention configuration
 * @param {Event} event
 */
async function saveRetention(event) {
    event.preventDefault();

    try {
        await api('/config/retention', {
            method: 'PUT',
            body: JSON.stringify({
                health_checks_days: getInputValue('retention-health'),
                api_calls_days: getInputValue('retention-api'),
                events_days: getInputValue('retention-events'),
                analytics_days: getInputValue('retention-analytics'),
            }),
        });

        alert('Retention settings saved');
    } catch (error) {
        alert('Failed to save: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
}

/**
 * Trigger retention enforcement
 */
async function enforceRetention() {
    if (!confirm('This will delete data older than the retention periods. Continue?')) {
        return;
    }

    try {
        const result = await api('/config/retention/enforce', { method: 'POST' });
        const deleted = result.deleted || {};
        const total = Object.values(deleted).reduce((a, b) => a + /** @type {number} */ (b), 0);
        alert(`Retention enforced. ${total} records deleted.`);
    } catch (error) {
        alert('Failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
}

/**
 * Load SSE statistics
 */
async function loadSSEStats() {
    try {
        const stats = await api('/sse/stats');
        const container = document.getElementById('sse-stats');
        if (!container) return;

        container.innerHTML = `
            <p>Active subscriptions: ${stats.active_subscriptions || 0}</p>
            <p>Status: ${stats.running ? 'Running' : 'Stopped'}</p>
        `;
    } catch (error) {
        console.error('Failed to load SSE stats:', error);
    }
}

/* ==========================================================================
   Simulation Mode
   ========================================================================== */

/**
 * Load simulation status and update UI
 */
async function loadSimulationStatus() {
    try {
        const status = await api('/simulation/status');
        updateSimulationUI(status);
    } catch (error) {
        console.error('Failed to load simulation status:', error);
    }
}

/**
 * Toggle simulation on/off
 * @param {boolean} enabled - Whether to enable simulation
 */
async function toggleSimulation(enabled) {
    const toggle = /** @type {HTMLInputElement} */ (document.getElementById('simulation-toggle'));
    const statusText = document.getElementById('simulation-status-text');

    try {
        if (statusText) statusText.textContent = enabled ? 'Starting...' : 'Stopping...';

        const endpoint = enabled ? '/simulation/start' : '/simulation/stop';
        await api(endpoint, { method: 'POST' });

        // Refresh status
        await loadSimulationStatus();
    } catch (error) {
        console.error('Simulation toggle failed:', error);
        if (toggle) toggle.checked = !enabled; // Revert toggle
        if (statusText) statusText.textContent = 'Error';
        alert('Failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
}

/**
 * Update simulation UI based on status
 * @param {Object} status - Simulation status from API
 */
function updateSimulationUI(status) {
    const toggle = /** @type {HTMLInputElement} */ (document.getElementById('simulation-toggle'));
    const statusText = document.getElementById('simulation-status-text');
    const statsEl = document.getElementById('simulation-stats');

    if (!status.available) {
        if (toggle) toggle.disabled = true;
        if (statusText) statusText.textContent = 'Not available';
        return;
    }

    if (toggle) {
        toggle.disabled = false;
        toggle.checked = status.running;
    }

    if (statusText) {
        statusText.textContent = status.running ? 'Active' : 'Inactive';
        statusText.className = status.running ? 'simulation-active' : '';
    }

    if (statsEl) {
        if (status.running && status.stats) {
            statsEl.textContent = `${status.stats.events_generated} events generated`;
            statsEl.classList.remove('hidden');
        } else {
            statsEl.classList.add('hidden');
        }
    }
}

/** @type {number | null} */
let simulationStatusInterval = null;

/**
 * Start polling simulation status (when running)
 */
function startSimulationPolling() {
    if (simulationStatusInterval) return;
    simulationStatusInterval = window.setInterval(async () => {
        const toggle = /** @type {HTMLInputElement} */ (document.getElementById('simulation-toggle'));
        if (toggle && toggle.checked) {
            await loadSimulationStatus();
        } else {
            stopSimulationPolling();
        }
    }, 2000);
}

/**
 * Stop polling simulation status
 */
function stopSimulationPolling() {
    if (simulationStatusInterval) {
        clearInterval(simulationStatusInterval);
        simulationStatusInterval = null;
    }
}

/* ==========================================================================
   Utility Functions
   ========================================================================== */

/**
 * Show an element
 * @param {string} id
 */
function showElement(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('hidden');
}

/**
 * Hide an element
 * @param {string} id
 */
function hideElement(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

/**
 * Set text content of an element
 * @param {string} id
 * @param {any} text
 */
function setTextContent(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(text);
}

/**
 * Set input value
 * @param {string} id
 * @param {any} value
 */
function setInputValue(id, value) {
    const el = /** @type {HTMLInputElement} */ (document.getElementById(id));
    if (el) el.value = String(value);
}

/**
 * Get input value as number
 * @param {string} id
 * @returns {number | null}
 */
function getInputValue(id) {
    const el = /** @type {HTMLInputElement} */ (document.getElementById(id));
    if (!el) return null;
    const val = parseInt(el.value, 10);
    return isNaN(val) ? null : val;
}

/**
 * Escape HTML
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Get CSS class for status
 * @param {string} status
 * @returns {string}
 */
function getStatusClass(status) {
    switch (status.toLowerCase()) {
        case 'healthy':
        case 'all_healthy':
            return 'healthy';
        case 'degraded':
        case 'some_degraded':
            return 'degraded';
        case 'unhealthy':
        case 'some_unhealthy':
        case 'all_unhealthy':
            return 'unhealthy';
        default:
            return 'unknown';
    }
}

/* ==========================================================================
   Initialization
   ========================================================================== */

// Make functions available globally for onclick handlers
// @ts-ignore
window.handleSetup = handleSetup;
// @ts-ignore
window.handleLogin = handleLogin;
// @ts-ignore
window.handleLogout = handleLogout;
// @ts-ignore
window.refreshHealth = refreshHealth;
// @ts-ignore
window.saveRetention = saveRetention;
// @ts-ignore
window.enforceRetention = enforceRetention;
// @ts-ignore
window.loadApiStats = loadApiStats;
// @ts-ignore
window.loadEvents = loadEvents;
// @ts-ignore
window.loadAnalyticsTenants = loadAnalyticsTenants;
// @ts-ignore
window.onTenantChange = onTenantChange;
// @ts-ignore
window.loadEmailStats = loadEmailStats;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    checkSetup();

    // Set up filter change handlers
    const apiHoursFilter = document.getElementById('api-hours-filter');
    if (apiHoursFilter) {
        apiHoursFilter.addEventListener('change', loadApiStats);
    }

    const eventFilters = ['event-entity-filter', 'event-type-filter', 'event-tenant-filter'];
    eventFilters.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', loadEvents);
        }
    });

    // Analytics filters
    const analyticsTenantFilter = document.getElementById('analytics-tenant-filter');
    if (analyticsTenantFilter) {
        analyticsTenantFilter.addEventListener('change', onTenantChange);
    }

    const analyticsDaysFilter = document.getElementById('analytics-days-filter');
    if (analyticsDaysFilter) {
        analyticsDaysFilter.addEventListener('change', () => {
            if (selectedTenantId) {
                loadAnalyticsData(selectedTenantId);
            }
        });
    }

    // Email filters
    const emailDaysFilter = document.getElementById('email-days-filter');
    if (emailDaysFilter) {
        emailDaysFilter.addEventListener('change', loadEmailStats);
    }
});
