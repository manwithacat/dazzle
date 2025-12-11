// @ts-check
/**
 * DNR-UI State Management - Reactive state stores
 * Part of the Dazzle Native Runtime
 *
 * @module state
 */

import { createSignal } from './signals.js';

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @typedef {'local'|'workspace'|'app'|'session'} StateScope
 * Scope levels for state storage:
 * - local: Component-local state
 * - workspace: Workspace-level state
 * - app: App-global state
 * - session: Session-persistent state (survives page refresh)
 */

/**
 * @typedef {Object} Notification
 * @property {string} id - Unique notification ID
 * @property {string} message - Notification message
 * @property {'info'|'success'|'warning'|'error'} [type] - Notification type
 */

// =============================================================================
// State Stores
// =============================================================================

/** @type {Record<StateScope, Map<string, [() => any, (v: any) => void]>>} */
const stateStores = {
  local: new Map(),     // Component-local state
  workspace: new Map(), // Workspace-level state
  app: new Map(),       // App-global state
  session: new Map()    // Session-persistent state
};

// Global loading and error state
const [globalLoading, setGlobalLoading] = createSignal(false);
const [globalError, setGlobalError] = createSignal(null);
const [notifications, setNotifications] = createSignal([]);

// =============================================================================
// State Access Functions
// =============================================================================

/**
 * Get state value at a given scope and path.
 *
 * @param {StateScope} scope - State scope level
 * @param {string} path - State path/key
 * @returns {any} Current state value or undefined
 *
 * @example
 * const count = getState('workspace', 'counter');
 */
export function getState(scope, path) {
  const store = stateStores[scope];
  if (!store) return undefined;
  const [getter] = store.get(path) || [];
  return getter ? getter() : undefined;
}

/**
 * Set state value at a given scope and path.
 * Creates the state if it doesn't exist.
 *
 * @param {StateScope} scope - State scope level
 * @param {string} path - State path/key
 * @param {any} value - New value
 *
 * @example
 * setState('workspace', 'counter', 42);
 */
export function setState(scope, path, value) {
  const store = stateStores[scope];
  if (!store) return;
  let [, setter] = store.get(path) || [];
  if (!setter) {
    // Auto-create state if it doesn't exist
    registerState(scope, path, value);
    [, setter] = store.get(path);
  }
  if (setter) setter(value);
}

/**
 * Update state with an updater function.
 *
 * @param {StateScope} scope - State scope level
 * @param {string} path - State path/key
 * @param {(prev: any) => any} updater - Function that receives current value and returns new value
 *
 * @example
 * updateState('workspace', 'counter', n => n + 1);
 */
export function updateState(scope, path, updater) {
  const store = stateStores[scope];
  if (!store) return;
  const [getter, setter] = store.get(path) || [];
  if (getter && setter) {
    setter(updater(getter()));
  }
}

/**
 * Register a new state slot with an initial value.
 *
 * @param {StateScope} scope - State scope level
 * @param {string} path - State path/key
 * @param {any} initial - Initial value
 * @param {boolean} [persistent=false] - Persist to localStorage
 * @returns {[() => any, (v: any) => void]} Signal tuple
 *
 * @example
 * const [getTheme, setTheme] = registerState('session', 'theme', 'light', true);
 */
export function registerState(scope, path, initial, persistent = false) {
  const store = stateStores[scope];
  if (!store.has(path)) {
    const signal = createSignal(initial, {
      persistent: persistent || scope === 'session',
      key: `${scope}_${path}`
    });
    store.set(path, signal);
  }
  return store.get(path);
}

// =============================================================================
// Global State Accessors
// =============================================================================

/**
 * Get global loading state.
 * @returns {boolean}
 */
export function getGlobalLoading() {
  return globalLoading();
}

/**
 * Set global loading state.
 * @param {boolean} value
 */
export function setGlobalLoadingState(value) {
  setGlobalLoading(value);
}

/**
 * Get global error state.
 * @returns {Error|null}
 */
export function getGlobalError() {
  return globalError();
}

/**
 * Set global error state.
 * @param {Error|null} value
 */
export function setGlobalErrorState(value) {
  setGlobalError(value);
}

/**
 * Get current notifications.
 * @returns {Notification[]}
 */
export function getNotifications() {
  return notifications();
}

/**
 * Add a notification to the stack.
 * @param {Notification} notification
 */
export function addNotification(notification) {
  setNotifications(prev => [...prev, notification]);
}

/**
 * Remove a notification by ID.
 * @param {string} id - Notification ID to remove
 */
export function removeNotification(id) {
  setNotifications(prev => prev.filter(n => n.id !== id));
}

// Export internal signals for direct access
export {
  globalLoading,
  globalError,
  notifications,
  setGlobalLoading,
  setGlobalError,
  setNotifications,
  stateStores
};
