// @ts-check
/**
 * Dazzle Bar - Developer overlay for persona switching and scenario control
 * Part of the Dazzle Native Runtime v0.8.5
 *
 * Entry point that initializes all Dazzle Bar components.
 *
 * @module dazzle-bar
 */

import { initDazzleBar, BAR_HEIGHT, BAR_ID, showToast } from './bar.js';
import {
  DazzleRuntime,
  isBarVisible,
  currentPersona,
  currentScenario,
  availablePersonas,
  availableScenarios,
  isLoading,
  error,
  fetchState
} from './runtime.js';

// =============================================================================
// Auto-initialization
// =============================================================================

/**
 * Initialize Dazzle Bar when DOM is ready.
 * Only initializes if the control plane is available (dev mode).
 */
async function autoInit() {
  // Check if control plane is available by making a test request
  try {
    const response = await fetch('/dazzle/dev/state');
    if (response.ok) {
      // Control plane is available, initialize the bar
      initDazzleBar();
    }
  } catch {
    // Control plane not available, skip initialization
    console.debug('[Dazzle Bar] Control plane not available, skipping initialization.');
  }
}

// Auto-init when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoInit);
} else {
  autoInit();
}

// =============================================================================
// Exports
// =============================================================================

export {
  // Initialization
  initDazzleBar,

  // Runtime API
  DazzleRuntime,

  // State signals
  isBarVisible,
  currentPersona,
  currentScenario,
  availablePersonas,
  availableScenarios,
  isLoading,
  error,

  // Functions
  fetchState,
  showToast,

  // Constants
  BAR_HEIGHT,
  BAR_ID
};

// Default export for convenient importing
export default DazzleRuntime;
