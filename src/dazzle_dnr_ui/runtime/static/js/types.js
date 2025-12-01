/**
 * DNR-UI Central Type Definitions
 *
 * This file defines shared data shapes for the DNR UI runtime.
 * Import types from here to ensure consistency across modules.
 *
 * @module types
 */

// =============================================================================
// Signal Types (from signals.js)
// =============================================================================

/**
 * @template T
 * @typedef {() => T} SignalGetter - Function that returns the current signal value
 */

/**
 * @template T
 * @typedef {(value: T | ((prev: T) => T)) => void} SignalSetter - Function to update signal value
 */

/**
 * @template T
 * @typedef {[SignalGetter<T>, SignalSetter<T>]} Signal - Tuple of getter and setter functions
 */

/**
 * @typedef {Object} SignalOptions
 * @property {boolean} [persistent] - Persist value to localStorage
 * @property {string} [key] - Storage key for persistence
 * @property {(a: any, b: any) => boolean} [equals] - Custom equality check
 */

/**
 * @typedef {Object} EffectOptions
 * @property {boolean} [defer] - Defer first execution to next animation frame
 */

/**
 * @template T
 * @typedef {Object} Resource
 * @property {SignalGetter<T|undefined>} data - The fetched data
 * @property {SignalGetter<boolean>} loading - Loading state
 * @property {SignalGetter<Error|null>} error - Error state
 * @property {(source?: any) => Promise<T>} refetch - Trigger a refetch
 */

// =============================================================================
// State Types (from state.js)
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
// API Types (from api-client.js)
// =============================================================================

/**
 * @typedef {Object} RequestOptions
 * @property {Record<string, string>} [headers] - Additional headers
 */

/**
 * @typedef {Object} ApiError
 * @property {number} status - HTTP status code
 * @property {any} data - Error response data
 * @property {string} message - Error message
 */

/**
 * @typedef {Object} PaginatedResponse
 * @property {Array<any>} items - List of items
 * @property {number} [total] - Total count
 * @property {number} [page] - Current page
 * @property {number} [page_size] - Items per page
 */

// =============================================================================
// Component Types
// =============================================================================

/**
 * @typedef {Object} ComponentContext
 * @property {string} [entityName] - Current entity name
 * @property {string} [surfaceName] - Current surface name
 * @property {Record<string, any>} [data] - Data context
 */

/**
 * @typedef {Object} FieldConfig
 * @property {string} name - Field name
 * @property {string} [label] - Display label
 * @property {string} type - Field type (text, number, boolean, etc.)
 * @property {boolean} [required] - Whether field is required
 * @property {any} [defaultValue] - Default value
 */

// =============================================================================
// DOM Types
// =============================================================================

/**
 * @typedef {Object} ElementProps
 * @property {string} [className] - CSS class names
 * @property {string} [id] - Element ID
 * @property {Record<string, string>} [style] - Inline styles
 * @property {Record<string, (e: Event) => void>} [on] - Event handlers
 */

export {};
