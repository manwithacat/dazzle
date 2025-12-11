// @ts-check
/**
 * Dazzle Bar Runtime - Global API for the Dazzle Bar developer overlay
 * Part of the Dazzle Native Runtime v0.8.5
 *
 * Provides DazzleRuntime global object for programmatic access to the bar.
 *
 * @module dazzle-bar/runtime
 */

import { createSignal, createEffect } from '../signals.js';

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @typedef {Object} Persona
 * @property {string} id - Persona identifier
 * @property {string} label - Display label
 * @property {string} [description] - Persona description
 * @property {string[]} [goals] - Persona goals
 * @property {'novice'|'intermediate'|'expert'} [proficiency] - Proficiency level
 * @property {string} [default_workspace] - Default workspace
 * @property {string} [default_route] - Default route
 */

/**
 * @typedef {Object} Scenario
 * @property {string} id - Scenario identifier
 * @property {string} name - Display name
 * @property {string} [description] - Scenario description
 */

/**
 * @typedef {Object} DazzleBarState
 * @property {string|null} current_persona - Current persona ID
 * @property {string|null} current_scenario - Current scenario ID
 * @property {Persona[]} available_personas - Available personas
 * @property {Scenario[]} available_scenarios - Available scenarios
 * @property {boolean} dev_mode - Whether dev mode is enabled
 */

/**
 * @typedef {Object} FeedbackPayload
 * @property {string} message - Feedback message
 * @property {string} [category] - Feedback category
 * @property {string} [route] - Current route
 * @property {Object<string, any>} [extra_context] - Additional context
 */

// =============================================================================
// State Signals
// =============================================================================

/** @type {import('../signals.js').Signal<boolean>} */
const [isBarVisible, setIsBarVisible] = createSignal(true);

/** @type {import('../signals.js').Signal<string|null>} */
const [currentPersona, setCurrentPersonaSignal] = createSignal(
  /** @type {string|null} */ (null)
);

/** @type {import('../signals.js').Signal<string|null>} */
const [currentScenario, setCurrentScenarioSignal] = createSignal(
  /** @type {string|null} */ (null)
);

/** @type {import('../signals.js').Signal<Persona[]>} */
const [availablePersonas, setAvailablePersonas] = createSignal(
  /** @type {Persona[]} */ ([])
);

/** @type {import('../signals.js').Signal<Scenario[]>} */
const [availableScenarios, setAvailableScenarios] = createSignal(
  /** @type {Scenario[]} */ ([])
);

/** @type {import('../signals.js').Signal<boolean>} */
const [isLoading, setIsLoading] = createSignal(false);

/** @type {import('../signals.js').Signal<string|null>} */
const [error, setError] = createSignal(/** @type {string|null} */ (null));

// =============================================================================
// API Client for Control Plane
// =============================================================================

const CONTROL_PLANE_BASE = '/dazzle/dev';

/**
 * Make a request to the control plane API.
 * @param {string} method - HTTP method
 * @param {string} path - API path
 * @param {any} [data] - Request body
 * @returns {Promise<any>}
 */
async function controlPlaneRequest(method, path, data = null) {
  const url = `${CONTROL_PLANE_BASE}${path}`;
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json'
    }
  };

  if (data && ['POST', 'PUT', 'PATCH'].includes(method)) {
    // @ts-ignore
    options.body = JSON.stringify(data);
  }

  const response = await fetch(url, options);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Control plane error: ${response.status} - ${errorText}`);
  }

  // Handle empty responses
  const text = await response.text();
  if (!text) return null;

  return JSON.parse(text);
}

// =============================================================================
// Core Runtime Functions
// =============================================================================

/**
 * Fetch the current Dazzle Bar state from the backend.
 * @returns {Promise<DazzleBarState>}
 */
async function fetchState() {
  setIsLoading(true);
  setError(null);

  try {
    const state = await controlPlaneRequest('GET', '/state');
    setCurrentPersonaSignal(state.current_persona);
    setCurrentScenarioSignal(state.current_scenario);
    setAvailablePersonas(state.available_personas || []);
    setAvailableScenarios(state.available_scenarios || []);
    return state;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to fetch state';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Set the current persona.
 * @param {string} personaId - Persona ID to set
 * @returns {Promise<void>}
 */
async function setCurrentPersona(personaId) {
  setIsLoading(true);
  setError(null);

  try {
    const result = await controlPlaneRequest('POST', '/current_persona', {
      persona_id: personaId
    });
    setCurrentPersonaSignal(result.persona_id);

    // Find persona and navigate to default route if available
    const persona = availablePersonas().find((p) => p.id === personaId);
    if (persona?.default_route && window.location.pathname !== persona.default_route) {
      window.location.pathname = persona.default_route;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to set persona';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Set the current scenario.
 * @param {string} scenarioId - Scenario ID to set
 * @returns {Promise<void>}
 */
async function setCurrentScenario(scenarioId) {
  setIsLoading(true);
  setError(null);

  try {
    const result = await controlPlaneRequest('POST', '/current_scenario', {
      scenario_id: scenarioId
    });
    setCurrentScenarioSignal(result.scenario_id);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to set scenario';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Reset all data in the database.
 * @returns {Promise<{status: string}>}
 */
async function resetData() {
  setIsLoading(true);
  setError(null);

  try {
    const result = await controlPlaneRequest('POST', '/reset');
    // Trigger a page refresh to reflect the changes
    window.location.reload();
    return result;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to reset data';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Regenerate demo data.
 * @param {Object} [options] - Regeneration options
 * @param {string} [options.scenario_id] - Target scenario
 * @param {Object<string, number>} [options.entity_counts] - Custom entity counts
 * @returns {Promise<{status: string, counts: Object<string, number>}>}
 */
async function regenerateData(options = {}) {
  setIsLoading(true);
  setError(null);

  try {
    const result = await controlPlaneRequest('POST', '/regenerate', options);
    // Trigger a page refresh to reflect the changes
    window.location.reload();
    return result;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to regenerate data';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Submit feedback.
 * @param {FeedbackPayload} feedback - Feedback data
 * @returns {Promise<{status: string, feedback_id: string}>}
 */
async function submitFeedback(feedback) {
  setIsLoading(true);
  setError(null);

  try {
    // Add current route if not provided
    const payload = {
      ...feedback,
      route: feedback.route || window.location.pathname,
      url: window.location.href,
      persona_id: currentPersona(),
      scenario_id: currentScenario()
    };

    const result = await controlPlaneRequest('POST', '/feedback', payload);
    return result;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to submit feedback';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Export session data.
 * @param {'github_issue'|'json'|'markdown'} [format='github_issue'] - Export format
 * @returns {Promise<{status: string, export_url?: string, export_data?: any}>}
 */
async function exportSession(format = 'github_issue') {
  setIsLoading(true);
  setError(null);

  try {
    const result = await controlPlaneRequest('POST', '/export', {
      export_format: format,
      include_feedback: true
    });

    // If GitHub issue URL, open in new tab
    if (result.export_url) {
      window.open(result.export_url, '_blank');
    }

    return result;
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to export session';
    setError(message);
    throw err;
  } finally {
    setIsLoading(false);
  }
}

/**
 * Get entity inspection data.
 * @returns {Promise<{entities: Array<{name: string, label: string, fields: any[], count: number}>}>}
 */
async function inspectEntities() {
  return controlPlaneRequest('GET', '/inspect/entities');
}

// =============================================================================
// Bar Visibility
// =============================================================================

/**
 * Toggle the Dazzle Bar visibility.
 */
function toggleBar() {
  setIsBarVisible(!isBarVisible());
}

/**
 * Show the Dazzle Bar.
 */
function showBar() {
  setIsBarVisible(true);
}

/**
 * Hide the Dazzle Bar.
 */
function hideBar() {
  setIsBarVisible(false);
}

// =============================================================================
// Global Runtime Object
// =============================================================================

/**
 * DazzleRuntime - Global API for the Dazzle Bar
 */
export const DazzleRuntime = {
  // State getters
  get currentPersona() {
    return currentPersona();
  },
  get currentScenario() {
    return currentScenario();
  },
  get availablePersonas() {
    return availablePersonas();
  },
  get availableScenarios() {
    return availableScenarios();
  },
  get isLoading() {
    return isLoading();
  },
  get error() {
    return error();
  },
  get isBarVisible() {
    return isBarVisible();
  },

  // Actions
  fetchState,
  setPersona: setCurrentPersona,
  setScenario: setCurrentScenario,
  resetData,
  regenerateData,
  submitFeedback,
  exportSession,
  inspectEntities,

  // Bar visibility
  toggleBar,
  showBar,
  hideBar
};

// Export signals for reactive components
export {
  isBarVisible,
  setIsBarVisible,
  currentPersona,
  setCurrentPersonaSignal as setCurrentPersona,
  currentScenario,
  setCurrentScenarioSignal as setCurrentScenario,
  availablePersonas,
  setAvailablePersonas,
  availableScenarios,
  setAvailableScenarios,
  isLoading,
  setIsLoading,
  error,
  setError,
  fetchState,
  controlPlaneRequest
};

// Make DazzleRuntime available globally
// @ts-ignore
window.DazzleRuntime = DazzleRuntime;
