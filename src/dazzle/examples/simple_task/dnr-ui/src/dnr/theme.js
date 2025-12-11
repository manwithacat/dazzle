/**
 * DNR-UI Theme System - CSS custom properties management
 * Part of the Dazzle Native Runtime
 */

// =============================================================================
// Theme Application
// =============================================================================

export function applyTheme(theme) {
  if (!theme || !theme.tokens) return;

  const root = document.documentElement;

  // Apply colors
  Object.entries(theme.tokens.colors || {}).forEach(([name, value]) => {
    root.style.setProperty(`--color-${name}`, value);
  });

  // Apply spacing
  Object.entries(theme.tokens.spacing || {}).forEach(([name, value]) => {
    root.style.setProperty(`--spacing-${name}`, typeof value === 'number' ? `${value}px` : value);
  });

  // Apply radii
  Object.entries(theme.tokens.radii || {}).forEach(([name, value]) => {
    root.style.setProperty(`--radius-${name}`, typeof value === 'number' ? `${value}px` : value);
  });
}

// =============================================================================
// Default Theme
// =============================================================================

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
