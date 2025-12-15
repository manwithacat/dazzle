/**
 * DNR-UI Theme System - CSS custom properties management
 * Part of the Dazzle Native Runtime
 *
 * Supports:
 * - Light/dark mode toggle
 * - System preference detection
 * - User preference persistence
 * - DaisyUI theme integration (data-theme attribute)
 *
 * @module theme
 */

// @ts-check

// =============================================================================
// Constants
// =============================================================================

const STORAGE_KEY = 'dz-theme-variant';
const THEME_LIGHT = 'light';
const THEME_DARK = 'dark';

// =============================================================================
// Theme State
// =============================================================================

/** @type {string} Current theme variant */
let currentVariant = THEME_LIGHT;

/** @type {((variant: string) => void)[]} Theme change listeners */
const listeners = [];

// =============================================================================
// System Preference Detection
// =============================================================================

/**
 * Get system preferred color scheme.
 * @returns {string} 'dark' or 'light'
 */
function getSystemPreference() {
  if (typeof window === 'undefined') return THEME_LIGHT;

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  return mediaQuery.matches ? THEME_DARK : THEME_LIGHT;
}

/**
 * Listen for system preference changes.
 * @param {(variant: string) => void} callback
 */
function onSystemPreferenceChange(callback) {
  if (typeof window === 'undefined') return;

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  mediaQuery.addEventListener('change', (e) => {
    // Only update if user hasn't set a manual preference
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      callback(e.matches ? THEME_DARK : THEME_LIGHT);
    }
  });
}

// =============================================================================
// Storage
// =============================================================================

/**
 * Get stored theme preference.
 * @returns {string|null}
 */
function getStoredPreference() {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEY);
}

/**
 * Store theme preference.
 * @param {string} variant
 */
function storePreference(variant) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, variant);
}

/**
 * Clear stored theme preference (revert to system).
 */
function clearStoredPreference() {
  if (typeof localStorage === 'undefined') return;
  localStorage.removeItem(STORAGE_KEY);
}

// =============================================================================
// DOM Updates
// =============================================================================

/**
 * Apply theme variant to DOM.
 * @param {string} variant - 'light' or 'dark'
 */
function applyVariantToDOM(variant) {
  const root = document.documentElement;

  // Set DaisyUI theme attribute
  root.setAttribute('data-theme', variant);

  // Also set color-scheme for native elements
  root.style.colorScheme = variant;

  // Add class for CSS targeting
  root.classList.remove('dz-theme-light', 'dz-theme-dark');
  root.classList.add(`dz-theme-${variant}`);
}

// =============================================================================
// Public API
// =============================================================================

/**
 * Initialize theme system.
 * Call this on page load to set up the theme.
 *
 * Priority:
 * 1. Stored user preference
 * 2. System preference (prefers-color-scheme)
 * 3. Default to light
 */
export function initTheme() {
  // Determine initial variant
  const stored = getStoredPreference();
  const system = getSystemPreference();
  const variant = stored || system || THEME_LIGHT;

  // Apply to DOM
  currentVariant = variant;
  applyVariantToDOM(variant);

  // Listen for system preference changes
  onSystemPreferenceChange((newVariant) => {
    setThemeVariant(newVariant);
  });

  return variant;
}

/**
 * Get current theme variant.
 * @returns {string} Current variant ('light' or 'dark')
 */
export function getThemeVariant() {
  return currentVariant;
}

/**
 * Set theme variant.
 * @param {string} variant - 'light' or 'dark'
 * @param {boolean} [persist=true] - Whether to persist preference
 */
export function setThemeVariant(variant, persist = true) {
  if (variant !== THEME_LIGHT && variant !== THEME_DARK) {
    console.warn(`Invalid theme variant: ${variant}. Using '${THEME_LIGHT}'.`);
    variant = THEME_LIGHT;
  }

  currentVariant = variant;
  applyVariantToDOM(variant);

  if (persist) {
    storePreference(variant);
  }

  // Notify listeners
  listeners.forEach(listener => listener(variant));
}

/**
 * Toggle between light and dark themes.
 * @returns {string} New variant
 */
export function toggleTheme() {
  const newVariant = currentVariant === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
  setThemeVariant(newVariant);
  return newVariant;
}

/**
 * Reset to system preference.
 */
export function resetToSystemPreference() {
  clearStoredPreference();
  const variant = getSystemPreference();
  setThemeVariant(variant, false);
}

/**
 * Add listener for theme changes.
 * @param {(variant: string) => void} callback
 * @returns {() => void} Unsubscribe function
 */
export function onThemeChange(callback) {
  listeners.push(callback);
  return () => {
    const index = listeners.indexOf(callback);
    if (index > -1) listeners.splice(index, 1);
  };
}

// =============================================================================
// Legacy API (backwards compatibility)
// =============================================================================

/**
 * Apply theme tokens to CSS custom properties.
 * @param {object} theme - Theme object with tokens
 * @deprecated Use initTheme() and setThemeVariant() instead
 */
export function applyTheme(theme) {
  if (!theme || !theme.tokens) return;

  const root = document.documentElement;

  // Apply colors
  Object.entries(theme.tokens.colors || {}).forEach(([name, value]) => {
    root.style.setProperty(`--color-${name}`, /** @type {string} */ (value));
  });

  // Apply spacing
  Object.entries(theme.tokens.spacing || {}).forEach(([name, value]) => {
    root.style.setProperty(`--spacing-${name}`, typeof value === 'number' ? `${value}px` : /** @type {string} */ (value));
  });

  // Apply radii
  Object.entries(theme.tokens.radii || {}).forEach(([name, value]) => {
    root.style.setProperty(`--radius-${name}`, typeof value === 'number' ? `${value}px` : /** @type {string} */ (value));
  });
}

/**
 * Default theme configuration.
 * @deprecated Theme tokens are now generated from ThemeSpec
 */
export const defaultTheme = {
  name: 'default',
  tokens: {
    colors: {
      primary: '#0066cc',
      secondary: '#6c757d',
      success: '#28a745',
      danger: '#dc3545',
      warning: '#ffc107',
      info: '#17a2b8',
      background: '#ffffff',
      surface: '#f8f9fa',
      text: '#212529',
      'text-secondary': '#6c757d',
      border: '#dee2e6'
    },
    spacing: {
      xs: 4,
      sm: 8,
      md: 16,
      lg: 24,
      xl: 32
    },
    radii: {
      sm: 2,
      md: 4,
      lg: 8
    }
  }
};

// =============================================================================
// Exports for Testing
// =============================================================================

export const _test = {
  STORAGE_KEY,
  THEME_LIGHT,
  THEME_DARK,
  getSystemPreference,
  getStoredPreference,
  clearStoredPreference,
};
