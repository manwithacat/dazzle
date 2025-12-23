/**
 * Dazzle Analytics - Lightweight native analytics
 *
 * Privacy-first analytics without third-party dependencies.
 * Uses sessionStorage (not cookies) and sendBeacon for reliable delivery.
 *
 * @ts-check
 */
'use strict';

/**
 * @typedef {Object} DazzleAnalyticsConfig
 * @property {string} [endpoint] - Analytics endpoint URL
 * @property {string} [tenantId] - Tenant ID for multi-tenant apps
 * @property {boolean} [trackPageViews] - Auto-track page views
 * @property {boolean} [trackClicks] - Track element clicks
 * @property {boolean} [trackForms] - Track form submissions
 * @property {string[]} [excludePaths] - Paths to exclude from tracking
 */

/**
 * @typedef {Object} PageViewData
 * @property {string} path
 * @property {string|null} title
 * @property {Object<string, string>} query
 * @property {string|null} referrer
 * @property {string} screen_size
 * @property {number|null} load_time_ms
 * @property {string} session_id
 * @property {string|null} tenant_id
 */

/**
 * @typedef {Object} EventData
 * @property {string} event_type
 * @property {string} event_name
 * @property {Object<string, any>} [properties]
 * @property {string} session_id
 * @property {string|null} tenant_id
 */

class DazzleAnalytics {
    /**
     * @param {DazzleAnalyticsConfig} [config]
     */
    constructor(config = {}) {
        /** @type {DazzleAnalyticsConfig} */
        this.config = {
            endpoint: '/_analytics',
            tenantId: null,
            trackPageViews: true,
            trackClicks: false,
            trackForms: true,
            excludePaths: ['/_ops/', '/health', '/static/'],
            ...config,
        };

        /** @type {string} */
        this.sessionId = this.getOrCreateSession();

        // Auto-tracking
        if (this.config.trackPageViews) {
            this.trackPageView();
            this.setupHistoryTracking();
        }

        if (this.config.trackClicks) {
            this.setupClickTracking();
        }

        if (this.config.trackForms) {
            this.setupFormTracking();
        }
    }

    /**
     * Get or create a session ID using sessionStorage
     * @returns {string}
     */
    getOrCreateSession() {
        const key = 'dz_session';
        let sessionId = sessionStorage.getItem(key);

        if (!sessionId) {
            sessionId = this.generateId();
            sessionStorage.setItem(key, sessionId);
        }

        return sessionId;
    }

    /**
     * Generate a unique ID
     * @returns {string}
     */
    generateId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        // Fallback for older browsers
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = (Math.random() * 16) | 0;
            const v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    /**
     * Check if the current path should be excluded
     * @returns {boolean}
     */
    shouldExclude() {
        const path = window.location.pathname;
        return this.config.excludePaths.some((exclude) => path.startsWith(exclude));
    }

    /**
     * Track a page view
     * @param {Object} [options]
     * @param {string} [options.path] - Override path
     * @param {string} [options.title] - Override title
     */
    trackPageView(options = {}) {
        if (this.shouldExclude()) {
            return;
        }

        const path = options.path || window.location.pathname;
        const title = options.title || document.title;

        /** @type {PageViewData} */
        const data = {
            path,
            title,
            query: this.getQueryParams(),
            referrer: document.referrer || null,
            screen_size: `${window.screen.width}x${window.screen.height}`,
            load_time_ms: this.getLoadTime(),
            session_id: this.sessionId,
            tenant_id: this.config.tenantId,
        };

        this.send('/beacon/pageview', data);
    }

    /**
     * Track a custom event
     * @param {string} eventType - Event category (e.g., 'click', 'form', 'action')
     * @param {string} eventName - Event name (e.g., 'signup_button')
     * @param {Object<string, any>} [properties] - Additional properties
     */
    trackEvent(eventType, eventName, properties = {}) {
        if (this.shouldExclude()) {
            return;
        }

        /** @type {EventData} */
        const data = {
            event_type: eventType,
            event_name: eventName,
            properties: {
                path: window.location.pathname,
                ...properties,
            },
            session_id: this.sessionId,
            tenant_id: this.config.tenantId,
        };

        this.send('/beacon/event', data);
    }

    /**
     * Track a click event
     * @param {string} elementId - ID or selector of the clicked element
     * @param {Object<string, any>} [properties] - Additional properties
     */
    trackClick(elementId, properties = {}) {
        this.trackEvent('click', elementId, properties);
    }

    /**
     * Track a form submission
     * @param {string} formName - Name of the form
     * @param {boolean} [success=true] - Whether submission was successful
     * @param {Object<string, any>} [properties] - Additional properties
     */
    trackFormSubmit(formName, success = true, properties = {}) {
        this.trackEvent('form_submit', formName, {
            success,
            ...properties,
        });
    }

    /**
     * Track a conversion event
     * @param {string} conversionName - Name of the conversion
     * @param {number} [value] - Optional value
     * @param {Object<string, any>} [properties] - Additional properties
     */
    trackConversion(conversionName, value = null, properties = {}) {
        this.trackEvent('conversion', conversionName, {
            value,
            ...properties,
        });
    }

    /**
     * Get query parameters as an object
     * @returns {Object<string, string>}
     */
    getQueryParams() {
        const params = {};
        const search = new URLSearchParams(window.location.search);
        search.forEach((value, key) => {
            params[key] = value;
        });
        return params;
    }

    /**
     * Get page load time in milliseconds
     * @returns {number|null}
     */
    getLoadTime() {
        if (typeof performance === 'undefined') {
            return null;
        }

        // Use Navigation Timing API v2 if available
        const entries = performance.getEntriesByType('navigation');
        if (entries.length > 0) {
            const nav = /** @type {PerformanceNavigationTiming} */ (entries[0]);
            return Math.round(nav.loadEventEnd - nav.startTime);
        }

        // Fallback to v1
        const timing = performance.timing;
        if (timing && timing.loadEventEnd > 0) {
            return timing.loadEventEnd - timing.navigationStart;
        }

        return null;
    }

    /**
     * Send data to the analytics endpoint
     * @param {string} path - API path
     * @param {Object} data - Data to send
     */
    send(path, data) {
        const url = `${this.config.endpoint}${path}`;
        const payload = JSON.stringify(data);

        // Prefer sendBeacon for reliability (works even on page unload)
        if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
            const blob = new Blob([payload], { type: 'application/json' });
            navigator.sendBeacon(url, blob);
        } else {
            // Fallback to fetch
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                keepalive: true,
            }).catch(() => {
                // Silently ignore errors
            });
        }
    }

    /**
     * Set up tracking for SPA navigation (History API)
     */
    setupHistoryTracking() {
        // Track pushState
        const originalPushState = history.pushState;
        history.pushState = (...args) => {
            originalPushState.apply(history, args);
            this.trackPageView();
        };

        // Track replaceState
        const originalReplaceState = history.replaceState;
        history.replaceState = (...args) => {
            originalReplaceState.apply(history, args);
            this.trackPageView();
        };

        // Track popstate (back/forward)
        window.addEventListener('popstate', () => {
            this.trackPageView();
        });
    }

    /**
     * Set up automatic click tracking for elements with data-track attribute
     */
    setupClickTracking() {
        document.addEventListener('click', (e) => {
            const target = /** @type {HTMLElement} */ (e.target);
            const tracked = target.closest('[data-track]');

            if (tracked) {
                const trackName =
                    tracked.getAttribute('data-track') ||
                    tracked.id ||
                    tracked.textContent?.trim().slice(0, 50) ||
                    'unknown';

                this.trackClick(trackName, {
                    element_type: tracked.tagName.toLowerCase(),
                    element_text: tracked.textContent?.trim().slice(0, 100),
                });
            }
        });
    }

    /**
     * Set up automatic form submission tracking
     */
    setupFormTracking() {
        document.addEventListener('submit', (e) => {
            const form = /** @type {HTMLFormElement} */ (e.target);
            const formName = form.getAttribute('data-track-form') || form.name || form.id || 'unknown_form';

            this.trackFormSubmit(formName, true, {
                form_action: form.action,
                form_method: form.method,
            });
        });
    }

    /**
     * Set the tenant ID for multi-tenant apps
     * @param {string} tenantId
     */
    setTenantId(tenantId) {
        this.config.tenantId = tenantId;
    }
}

// Auto-initialize if script is included directly
if (typeof window !== 'undefined') {
    // Check for configuration in global scope
    const config = window['DazzleAnalyticsConfig'] || {};

    // Create global instance
    window['dazzleAnalytics'] = new DazzleAnalytics(config);

}
