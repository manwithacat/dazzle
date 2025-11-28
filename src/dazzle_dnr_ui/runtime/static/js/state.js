/**
 * DNR-UI State Management - Reactive state stores
 * Part of the Dazzle Native Runtime
 */

import { createSignal } from './signals.js';

// =============================================================================
// State Stores
// =============================================================================

const stateStores = {
  local: new Map(),    // Component-local state
  workspace: new Map(), // Workspace-level state
  app: new Map(),      // App-global state
  session: new Map()   // Session-persistent state
};

// Global loading and error state
const [globalLoading, setGlobalLoading] = createSignal(false);
const [globalError, setGlobalError] = createSignal(null);
const [notifications, setNotifications] = createSignal([]);

// =============================================================================
// State Access Functions
// =============================================================================

export function getState(scope, path) {
  const store = stateStores[scope];
  if (!store) return undefined;
  const [getter] = store.get(path) || [];
  return getter ? getter() : undefined;
}

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

export function updateState(scope, path, updater) {
  const store = stateStores[scope];
  if (!store) return;
  const [getter, setter] = store.get(path) || [];
  if (getter && setter) {
    setter(updater(getter()));
  }
}

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

export function getGlobalLoading() {
  return globalLoading();
}

export function setGlobalLoadingState(value) {
  setGlobalLoading(value);
}

export function getGlobalError() {
  return globalError();
}

export function setGlobalErrorState(value) {
  setGlobalError(value);
}

export function getNotifications() {
  return notifications();
}

export function addNotification(notification) {
  setNotifications(prev => [...prev, notification]);
}

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
