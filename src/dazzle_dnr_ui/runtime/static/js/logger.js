// @ts-check
/**
 * DNR-UI Logger - Frontend error capture and logging
 * Part of the Dazzle Native Runtime
 *
 * Captures JavaScript errors, unhandled rejections, and console messages,
 * sending them to the backend logging infrastructure for LLM agent inspection.
 *
 * @module logger
 */

// =============================================================================
// Configuration
// =============================================================================

/** @type {string} */
const LOG_ENDPOINT = '/dazzle/dev/log';

/** @type {boolean} */
let isInitialized = false;

/** @type {boolean} */
let isEnabled = true;

// =============================================================================
// Types
// =============================================================================

/**
 * @typedef {Object} LogEntry
 * @property {'error'|'warn'|'info'|'debug'|'log'} level - Log level
 * @property {string} message - Log message
 * @property {string} [source] - Source file URL
 * @property {number} [line] - Line number
 * @property {number} [column] - Column number
 * @property {string} [stack] - Stack trace
 * @property {string} [url] - Page URL
 * @property {string} [user_agent] - Browser user agent
 * @property {Object<string, any>} [extra] - Additional context
 */

// =============================================================================
// Core Logging Functions
// =============================================================================

/**
 * Send a log entry to the backend.
 * @param {LogEntry} entry - Log entry to send
 * @returns {Promise<void>}
 */
async function sendLog(entry) {
  if (!isEnabled) return;

  try {
    // Add context
    const payload = {
      ...entry,
      url: entry.url || window.location.href,
      user_agent: entry.user_agent || navigator.userAgent
    };

    await fetch(LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch {
    // Silently fail - don't cause cascading errors from logging
  }
}

/**
 * Log an error.
 * @param {string} message - Error message
 * @param {Object} [context] - Additional context
 * @returns {void}
 */
export function logError(message, context = {}) {
  const entry = {
    level: /** @type {const} */ ('error'),
    message,
    extra: context
  };
  sendLog(entry);
}

/**
 * Log a warning.
 * @param {string} message - Warning message
 * @param {Object} [context] - Additional context
 * @returns {void}
 */
export function logWarning(message, context = {}) {
  const entry = {
    level: /** @type {const} */ ('warn'),
    message,
    extra: context
  };
  sendLog(entry);
}

/**
 * Log an info message.
 * @param {string} message - Info message
 * @param {Object} [context] - Additional context
 * @returns {void}
 */
export function logInfo(message, context = {}) {
  const entry = {
    level: /** @type {const} */ ('info'),
    message,
    extra: context
  };
  sendLog(entry);
}

/**
 * Log a debug message.
 * @param {string} message - Debug message
 * @param {Object} [context] - Additional context
 * @returns {void}
 */
export function logDebug(message, context = {}) {
  const entry = {
    level: /** @type {const} */ ('debug'),
    message,
    extra: context
  };
  sendLog(entry);
}

// =============================================================================
// Error Handlers
// =============================================================================

/**
 * Handle uncaught errors.
 * @param {ErrorEvent} event - Error event
 */
function handleError(event) {
  const entry = {
    level: /** @type {const} */ ('error'),
    message: event.message || 'Unknown error',
    source: event.filename,
    line: event.lineno,
    column: event.colno,
    stack: event.error?.stack,
    extra: {
      type: 'uncaught_error'
    }
  };
  sendLog(entry);
}

/**
 * Handle unhandled promise rejections.
 * @param {PromiseRejectionEvent} event - Rejection event
 */
function handleUnhandledRejection(event) {
  const reason = event.reason;
  let message = 'Unhandled Promise rejection';
  let stack;

  if (reason instanceof Error) {
    message = reason.message;
    stack = reason.stack;
  } else if (typeof reason === 'string') {
    message = reason;
  } else if (reason) {
    message = String(reason);
  }

  const entry = {
    level: /** @type {const} */ ('error'),
    message,
    stack,
    extra: {
      type: 'unhandled_rejection'
    }
  };
  sendLog(entry);
}

// =============================================================================
// Console Interception
// =============================================================================

/** @type {typeof console.error} */
let originalConsoleError;

/** @type {typeof console.warn} */
let originalConsoleWarn;

/**
 * Intercept console.error and console.warn to capture to log file.
 */
function interceptConsole() {
  originalConsoleError = console.error;
  originalConsoleWarn = console.warn;

  console.error = function (...args) {
    // Call original
    originalConsoleError.apply(console, args);

    // Log to backend
    const message = args
      .map((arg) => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg)))
      .join(' ');

    sendLog({
      level: 'error',
      message,
      extra: { type: 'console_error' }
    });
  };

  console.warn = function (...args) {
    // Call original
    originalConsoleWarn.apply(console, args);

    // Log to backend
    const message = args
      .map((arg) => (typeof arg === 'object' ? JSON.stringify(arg) : String(arg)))
      .join(' ');

    sendLog({
      level: 'warn',
      message,
      extra: { type: 'console_warn' }
    });
  };
}

/**
 * Restore original console methods.
 */
function restoreConsole() {
  if (originalConsoleError) {
    console.error = originalConsoleError;
  }
  if (originalConsoleWarn) {
    console.warn = originalConsoleWarn;
  }
}

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize the logger.
 * Sets up error handlers and console interception.
 * @param {Object} [options] - Initialization options
 * @param {boolean} [options.interceptConsole=true] - Whether to intercept console.error/warn
 * @returns {void}
 */
export function initLogger(options = {}) {
  if (isInitialized) return;

  const { interceptConsole: shouldIntercept = true } = options;

  // Set up global error handlers
  window.addEventListener('error', handleError);
  window.addEventListener('unhandledrejection', handleUnhandledRejection);

  // Optionally intercept console
  if (shouldIntercept) {
    interceptConsole();
  }

  isInitialized = true;

  // Log initialization
  logInfo('Frontend logger initialized', {
    url: window.location.href,
    timestamp: new Date().toISOString()
  });
}

/**
 * Disable the logger.
 * @returns {void}
 */
export function disableLogger() {
  isEnabled = false;
  restoreConsole();
  window.removeEventListener('error', handleError);
  window.removeEventListener('unhandledrejection', handleUnhandledRejection);
  isInitialized = false;
}

/**
 * Enable the logger.
 * @returns {void}
 */
export function enableLogger() {
  isEnabled = true;
  if (!isInitialized) {
    initLogger();
  }
}

// =============================================================================
// Exports
// =============================================================================

export const logger = {
  error: logError,
  warn: logWarning,
  info: logInfo,
  debug: logDebug,
  init: initLogger,
  disable: disableLogger,
  enable: enableLogger
};

export default logger;
