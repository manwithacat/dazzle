"""
Vite project generator for DNR-UI runtime.

Generates a Vite-bundled application from UISpec while keeping
the pure JavaScript, no-framework approach.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle_dnr_ui.specs import UISpec


# =============================================================================
# ES Module Runtime Templates
# =============================================================================

SIGNALS_JS = '''/**
 * DNR Signals - Reactive primitives
 * Pure JavaScript signals implementation
 */

let currentSubscriber = null;

/**
 * Create a reactive signal
 * @param {any} initialValue - Initial signal value
 * @param {Object} options - Signal options
 * @param {boolean} options.persistent - Persist to localStorage
 * @param {string} options.key - Storage key for persistence
 * @returns {[Function, Function]} - [getter, setter] tuple
 */
export function createSignal(initialValue, options = {}) {
  let value = initialValue;
  const subscribers = new Set();
  const { persistent, key } = options;

  // Load from storage if persistent
  if (persistent && key) {
    const stored = localStorage.getItem(`dnr_${key}`);
    if (stored !== null) {
      try {
        value = JSON.parse(stored);
      } catch (e) {
        console.warn(`Failed to parse stored value for ${key}`, e);
      }
    }
  }

  function getter() {
    if (currentSubscriber) {
      subscribers.add(currentSubscriber);
    }
    return value;
  }

  function setter(newValue) {
    if (typeof newValue === 'function') {
      newValue = newValue(value);
    }
    if (value !== newValue) {
      value = newValue;
      // Persist if needed
      if (persistent && key) {
        localStorage.setItem(`dnr_${key}`, JSON.stringify(value));
      }
      // Notify subscribers
      subscribers.forEach(fn => fn());
    }
  }

  return [getter, setter];
}

/**
 * Create a reactive effect
 * @param {Function} fn - Effect function to run
 */
export function createEffect(fn) {
  function execute() {
    currentSubscriber = execute;
    try {
      fn();
    } finally {
      currentSubscriber = null;
    }
  }
  execute();
}

/**
 * Create a memoized computed value
 * @param {Function} fn - Computation function
 * @returns {Function} - Getter for computed value
 */
export function createMemo(fn) {
  let cachedValue;
  let dirty = true;

  createEffect(() => {
    dirty = true;
  });

  return function() {
    if (dirty) {
      cachedValue = fn();
      dirty = false;
    }
    return cachedValue;
  };
}
'''

STATE_JS = '''/**
 * DNR State Management
 * Scoped state stores with signals
 */

import { createSignal } from './signals.js';

// State stores for different scopes
const stateStores = {
  local: new Map(),     // Component-local state
  workspace: new Map(), // Workspace-level state
  app: new Map(),       // App-global state
  session: new Map()    // Session-persistent state
};

/**
 * Get state value by scope and path
 */
export function getState(scope, path) {
  const store = stateStores[scope];
  if (!store) return undefined;
  const [getter] = store.get(path) || [];
  return getter ? getter() : undefined;
}

/**
 * Set state value by scope and path
 */
export function setState(scope, path, value) {
  const store = stateStores[scope];
  if (!store) return;
  const [, setter] = store.get(path) || [];
  if (setter) setter(value);
}

/**
 * Register a new state variable
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

/**
 * Clear all state in a scope
 */
export function clearState(scope) {
  const store = stateStores[scope];
  if (store) store.clear();
}

export { stateStores };
'''

DOM_JS = '''/**
 * DNR DOM Utilities
 * Pure DOM manipulation helpers
 */

import { createEffect } from './signals.js';

/**
 * Create a DOM element with props and children
 */
export function createElement(tag, props = {}, children = []) {
  const el = document.createElement(tag);

  Object.entries(props).forEach(([key, value]) => {
    if (key === 'className') {
      el.className = value;
    } else if (key === 'style' && typeof value === 'object') {
      Object.assign(el.style, value);
    } else if (key.startsWith('on') && typeof value === 'function') {
      const event = key.slice(2).toLowerCase();
      el.addEventListener(event, value);
    } else if (key === 'ref' && typeof value === 'function') {
      value(el);
    } else if (value !== null && value !== undefined && value !== false) {
      el.setAttribute(key, value);
    }
  });

  children.forEach(child => {
    if (typeof child === 'string' || typeof child === 'number') {
      el.appendChild(document.createTextNode(String(child)));
    } else if (child instanceof Node) {
      el.appendChild(child);
    } else if (Array.isArray(child)) {
      child.forEach(c => {
        if (c instanceof Node) el.appendChild(c);
        else if (c != null) el.appendChild(document.createTextNode(String(c)));
      });
    }
  });

  return el;
}

/**
 * Render a component into a container
 */
export function render(container, component) {
  container.innerHTML = '';
  if (component instanceof Node) {
    container.appendChild(component);
  } else if (typeof component === 'function') {
    createEffect(() => {
      container.innerHTML = '';
      const result = component();
      if (result instanceof Node) {
        container.appendChild(result);
      }
    });
  }
}

/**
 * Get nested value by path
 */
export function getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((o, p) => o && o[p], obj);
}
'''

BINDINGS_JS = '''/**
 * DNR Binding Resolution
 * Resolve data bindings to values
 */

import { getState, stateStores } from './state.js';
import { getByPath } from './dom.js';

/**
 * Resolve a binding to its value
 */
export function resolveBinding(binding, context) {
  if (!binding || !binding.kind) return binding;

  switch (binding.kind) {
    case 'literal':
      return binding.value;

    case 'prop':
      return getByPath(context.props, binding.path);

    case 'state':
      return getState('local', `${context.componentId}_${binding.path}`);

    case 'workspaceState':
      return getState('workspace', binding.path);

    case 'appState':
      return getState('app', binding.path);

    case 'derived':
      try {
        return evalExpression(binding.expr, context);
      } catch (e) {
        console.warn('Expression evaluation failed:', binding.expr, e);
        return undefined;
      }

    default:
      return binding;
  }
}

/**
 * Evaluate a derived expression
 */
export function evalExpression(expr, context) {
  const fn = new Function('ctx', `with(ctx) { return ${expr}; }`);
  return fn({
    props: context.props || {},
    state: context.state || {},
    workspace: stateStores.workspace,
    app: stateStores.app
  });
}
'''

COMPONENTS_JS = '''/**
 * DNR Component Registry & Built-in Components
 * Pure JavaScript UI components
 */

import { createElement } from './dom.js';

// Component registry
const componentRegistry = new Map();

/**
 * Register a component
 */
export function registerComponent(name, renderFn) {
  componentRegistry.set(name, renderFn);
}

/**
 * Get a registered component
 */
export function getComponent(name) {
  return componentRegistry.get(name);
}

/**
 * Check if component exists
 */
export function hasComponent(name) {
  return componentRegistry.has(name);
}

// =============================================================================
// Built-in Primitives
// =============================================================================

// Page component
registerComponent('Page', (props, children) => {
  return createElement('div', {
    className: 'dnr-page',
    style: { padding: 'var(--spacing-md, 16px)' }
  }, [
    props.title ? createElement('h1', { className: 'dnr-page-title' }, [props.title]) : null,
    ...children
  ].filter(Boolean));
});

// Card component
registerComponent('Card', (props, children) => {
  return createElement('div', {
    className: 'dnr-card',
    style: {
      border: '1px solid var(--color-border, #ddd)',
      borderRadius: 'var(--radius-md, 4px)',
      padding: 'var(--spacing-md, 16px)',
      backgroundColor: 'var(--color-surface, #fff)'
    }
  }, [
    props.title ? createElement('h2', { className: 'dnr-card-title' }, [props.title]) : null,
    ...children
  ].filter(Boolean));
});

// Text component
registerComponent('Text', (props, children) => {
  const tag = props.variant === 'heading' ? 'h2' :
              props.variant === 'subheading' ? 'h3' :
              props.variant === 'label' ? 'label' : 'p';
  return createElement(tag, { className: `dnr-text dnr-text-${props.variant || 'body'}` }, children);
});

// Button component
registerComponent('Button', (props, children) => {
  return createElement('button', {
    className: `dnr-button dnr-button-${props.variant || 'default'}`,
    onClick: props.onClick,
    disabled: props.disabled,
    type: props.type || 'button',
    style: {
      padding: 'var(--spacing-sm, 8px) var(--spacing-md, 16px)',
      borderRadius: 'var(--radius-sm, 2px)',
      cursor: props.disabled ? 'not-allowed' : 'pointer'
    }
  }, children.length ? children : [props.label]);
});

// Input component
registerComponent('Input', (props) => {
  return createElement('input', {
    className: 'dnr-input',
    type: props.type || 'text',
    value: props.value,
    placeholder: props.placeholder,
    disabled: props.disabled,
    onInput: (e) => props.onChange && props.onChange(e.target.value),
    style: {
      padding: 'var(--spacing-sm, 8px)',
      border: '1px solid var(--color-border, #ddd)',
      borderRadius: 'var(--radius-sm, 2px)',
      width: '100%'
    }
  });
});

// DataTable component
registerComponent('DataTable', (props) => {
  const { columns, data, onRowClick } = props;

  const thead = createElement('thead', {}, [
    createElement('tr', {}, (columns || []).map(col =>
      createElement('th', { style: { textAlign: 'left', padding: '8px' } }, [col.label || col.key])
    ))
  ]);

  const tbody = createElement('tbody', {}, (data || []).map((row, idx) =>
    createElement('tr', {
      onClick: () => onRowClick && onRowClick(row),
      style: { cursor: onRowClick ? 'pointer' : 'default' }
    }, (columns || []).map(col =>
      createElement('td', { style: { padding: '8px' } }, [row[col.key]])
    ))
  ));

  return createElement('table', {
    className: 'dnr-data-table',
    style: { width: '100%', borderCollapse: 'collapse' }
  }, [thead, tbody]);
});

// Form component
registerComponent('Form', (props, children) => {
  return createElement('form', {
    className: 'dnr-form',
    onSubmit: (e) => {
      e.preventDefault();
      props.onSubmit && props.onSubmit(e);
    }
  }, [
    props.title ? createElement('h2', { className: 'dnr-form-title' }, [props.title]) : null,
    ...children
  ].filter(Boolean));
});

// Stack (flexbox) component
registerComponent('Stack', (props, children) => {
  return createElement('div', {
    className: 'dnr-stack',
    style: {
      display: 'flex',
      flexDirection: props.direction || 'column',
      gap: `var(--spacing-${props.gap || 'md'}, 16px)`,
      alignItems: props.align || 'stretch',
      justifyContent: props.justify || 'flex-start'
    }
  }, children);
});

// FilterableTable pattern component
registerComponent('FilterableTable', (props) => {
  return createElement('div', { className: 'dnr-filterable-table' }, [
    createElement('div', { className: 'dnr-filters', style: { marginBottom: '16px' } }, [
      props.filterPlaceholder ?
        createElement('input', {
          type: 'text',
          placeholder: props.filterPlaceholder,
          style: { padding: '8px', width: '200px' }
        }) : null
    ].filter(Boolean)),
    getComponent('DataTable')(props)
  ]);
});

export { componentRegistry };
'''

RENDERER_JS = '''/**
 * DNR View Tree Renderer
 * Render view nodes to DOM
 */

import { resolveBinding } from './bindings.js';
import { getComponent, hasComponent } from './components.js';
import { createElement, getByPath } from './dom.js';

/**
 * Render a view node
 */
export function renderViewNode(node, context) {
  if (!node) return null;

  switch (node.kind) {
    case 'element':
      return renderElementNode(node, context);

    case 'conditional':
      return renderConditionalNode(node, context);

    case 'loop':
      return renderLoopNode(node, context);

    case 'slot':
      return renderSlotNode(node, context);

    case 'text':
      return renderTextNode(node, context);

    default:
      console.warn('Unknown node kind:', node.kind);
      return null;
  }
}

/**
 * Render an element node
 */
function renderElementNode(node, context) {
  const componentName = node.as || node.as_;
  const ComponentFn = getComponent(componentName);

  // Resolve all props
  const resolvedProps = {};
  Object.entries(node.props || {}).forEach(([key, binding]) => {
    resolvedProps[key] = resolveBinding(binding, context);
  });

  // Render children
  const children = (node.children || []).map(child => renderViewNode(child, context)).filter(Boolean);

  if (ComponentFn) {
    return ComponentFn(resolvedProps, children);
  } else {
    // Fall back to HTML element
    return createElement(componentName.toLowerCase(), resolvedProps, children);
  }
}

/**
 * Render a conditional node
 */
function renderConditionalNode(node, context) {
  const condition = resolveBinding(node.condition, context);
  if (condition) {
    return renderViewNode(node.then_branch || node.thenBranch, context);
  } else if (node.else_branch || node.elseBranch) {
    return renderViewNode(node.else_branch || node.elseBranch, context);
  }
  return null;
}

/**
 * Render a loop node
 */
function renderLoopNode(node, context) {
  const items = resolveBinding(node.items, context) || [];
  const itemVar = node.item_var || node.itemVar || 'item';
  const keyPath = node.key_path || node.keyPath || 'id';

  const fragment = document.createDocumentFragment();
  items.forEach((item, index) => {
    const itemContext = {
      ...context,
      props: {
        ...context.props,
        [itemVar]: item,
        [`${itemVar}Index`]: index
      }
    };
    const child = renderViewNode(node.template, itemContext);
    if (child) {
      child.setAttribute && child.setAttribute('data-key', getByPath(item, keyPath) || index);
      fragment.appendChild(child);
    }
  });
  return fragment;
}

/**
 * Render a slot node
 */
function renderSlotNode(node, context) {
  const slotContent = context.slots && context.slots[node.name];
  if (slotContent) {
    return renderViewNode(slotContent, context);
  } else if (node.fallback) {
    return renderViewNode(node.fallback, context);
  }
  return null;
}

/**
 * Render a text node
 */
function renderTextNode(node, context) {
  const content = resolveBinding(node.content, context);
  return document.createTextNode(String(content || ''));
}
'''

THEME_JS = '''/**
 * DNR Theme System
 * CSS custom property based theming
 */

/**
 * Apply a theme to the document
 */
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

  // Apply typography
  if (theme.tokens.typography) {
    Object.entries(theme.tokens.typography).forEach(([name, style]) => {
      if (style.fontSize) root.style.setProperty(`--font-size-${name}`, style.fontSize);
      if (style.fontWeight) root.style.setProperty(`--font-weight-${name}`, style.fontWeight);
      if (style.lineHeight) root.style.setProperty(`--line-height-${name}`, style.lineHeight);
    });
  }
}

/**
 * Get current theme value
 */
export function getThemeValue(property) {
  return getComputedStyle(document.documentElement).getPropertyValue(property).trim();
}
'''

ACTIONS_JS = '''/**
 * DNR Action Execution
 * Handle user actions and effects
 */

import { resolveBinding } from './bindings.js';
import { setState } from './state.js';

/**
 * Execute an action
 */
export async function executeAction(action, context) {
  if (!action) return;

  // Apply state transitions
  if (action.transitions) {
    action.transitions.forEach(transition => {
      const scope = transition.scope || 'local';
      const path = scope === 'local' ?
        `${context.componentId}_${transition.target_state || transition.targetState}` :
        (transition.target_state || transition.targetState);

      setState(scope, path, transition.update || transition.value);
    });
  }

  // Execute effect
  if (action.effect) {
    await executeEffect(action.effect, context);
  }
}

/**
 * Execute an effect
 */
export async function executeEffect(effect, context) {
  if (!effect) return;

  switch (effect.kind) {
    case 'fetch':
      try {
        const response = await fetch(`/api/${effect.backend_service || effect.backendService}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(context.data || {})
        });
        const data = await response.json();
        if (effect.on_success || effect.onSuccess) {
          const successAction = context.getAction(effect.on_success || effect.onSuccess);
          if (successAction) {
            await executeAction(successAction, { ...context, data });
          }
        }
      } catch (error) {
        if (effect.on_error || effect.onError) {
          const errorAction = context.getAction(effect.on_error || effect.onError);
          if (errorAction) {
            await executeAction(errorAction, { ...context, error });
          }
        }
      }
      break;

    case 'navigate':
      const route = effect.route;
      const params = {};
      Object.entries(effect.params || {}).forEach(([key, binding]) => {
        params[key] = resolveBinding(binding, context);
      });
      let url = route;
      Object.entries(params).forEach(([key, value]) => {
        url = url.replace(`{${key}}`, encodeURIComponent(value));
      });
      window.history.pushState({}, '', url);
      window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url } }));
      break;

    case 'log':
      console.log(resolveBinding(effect.message, context));
      break;

    case 'toast':
      // TODO: Replace with proper toast component
      alert(resolveBinding(effect.message, context));
      break;
  }
}
'''

APP_JS = '''/**
 * DNR Application Bootstrap
 * Main application entry point
 */

import { registerState } from './state.js';
import { render } from './dom.js';
import { registerComponent, getComponent, hasComponent } from './components.js';
import { renderViewNode } from './renderer.js';
import { applyTheme } from './theme.js';
import { getState, setState } from './state.js';

/**
 * Create a DNR application from a UISpec
 */
export function createApp(uiSpec) {
  // Register custom components from spec
  (uiSpec.components || []).forEach(comp => {
    if (comp.view && !hasComponent(comp.name)) {
      registerComponent(comp.name, (props, children) => {
        // Initialize component state
        (comp.state || []).forEach(stateSpec => {
          const scope = stateSpec.scope || 'local';
          const path = scope === 'local' ? `${comp.name}_${stateSpec.name}` : stateSpec.name;
          registerState(scope, path, stateSpec.initial, stateSpec.persistent);
        });

        // Build context
        const context = {
          componentId: comp.name,
          props,
          slots: {},
          getAction: (name) => (comp.actions || []).find(a => a.name === name)
        };

        // Render view tree
        return renderViewNode(comp.view, context);
      });
    }
  });

  // Apply default theme
  if (uiSpec.default_theme || uiSpec.defaultTheme) {
    const themeName = uiSpec.default_theme || uiSpec.defaultTheme;
    const theme = (uiSpec.themes || []).find(t => t.name === themeName);
    if (theme) applyTheme(theme);
  }

  return {
    mount(container, workspaceName) {
      const workspace = (uiSpec.workspaces || []).find(w => w.name === workspaceName);
      if (!workspace) {
        console.error(`Workspace "${workspaceName}" not found`);
        return;
      }

      // Initialize workspace state
      (workspace.state || []).forEach(stateSpec => {
        registerState('workspace', stateSpec.name, stateSpec.initial, stateSpec.persistent);
      });

      // Render workspace routes
      const defaultRoute = workspace.routes && workspace.routes[0];
      if (defaultRoute) {
        const ComponentFn = getComponent(defaultRoute.component);
        if (ComponentFn) {
          render(container, () => ComponentFn({}, []));
        }
      }
    },

    navigate(route) {
      window.history.pushState({}, '', route);
      window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url: route } }));
    },

    getState,
    setState,
    registerComponent,
    applyTheme
  };
}
'''

INDEX_JS = '''/**
 * DNR-UI Runtime
 * Main export file
 */

// Signals
export { createSignal, createEffect, createMemo } from './signals.js';

// State
export { getState, setState, registerState, clearState } from './state.js';

// DOM
export { createElement, render, getByPath } from './dom.js';

// Components
export { registerComponent, getComponent, hasComponent } from './components.js';

// Renderer
export { renderViewNode } from './renderer.js';

// Theme
export { applyTheme, getThemeValue } from './theme.js';

// Actions
export { executeAction, executeEffect } from './actions.js';

// App
export { createApp } from './app.js';
'''


# =============================================================================
# Configuration Templates
# =============================================================================

VITE_CONFIG_JS = '''import { defineConfig } from 'vite';

export default defineConfig({
  root: 'src',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  resolve: {
    alias: {
      '@dnr': '/dnr'
    }
  }
});
'''

PACKAGE_JSON_TEMPLATE = '''{{
  "name": "{name}",
  "version": "1.0.0",
  "description": "DNR-UI Application - Generated by Dazzle",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "serve": "vite preview --port 3000"
  }},
  "devDependencies": {{
    "vite": "^5.0.0"
  }}
}}
'''

INDEX_HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="/styles/dnr.css">
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/main.js"></script>
</body>
</html>
'''

MAIN_JS_TEMPLATE = '''/**
 * Application Entry Point
 * Generated by Dazzle Native Runtime
 */

import { createApp } from '@dnr/app.js';
import uiSpec from './ui-spec.json';

// Initialize app on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const app = createApp(uiSpec);

  // Mount default workspace
  const container = document.getElementById('app') || document.body;
  const defaultWorkspace = uiSpec.default_workspace || uiSpec.defaultWorkspace ||
                          (uiSpec.workspaces?.[0]?.name);

  if (defaultWorkspace) {
    app.mount(container, defaultWorkspace);
  }

  // Export app for debugging
  window.dnrApp = app;
});
'''

DNR_CSS = '''/* DNR-UI Base Styles */
:root {
  --color-primary: #0066cc;
  --color-secondary: #6c757d;
  --color-success: #28a745;
  --color-danger: #dc3545;
  --color-warning: #ffc107;
  --color-info: #17a2b8;
  --color-background: #ffffff;
  --color-surface: #f8f9fa;
  --color-text: #212529;
  --color-text-secondary: #6c757d;
  --color-border: #dee2e6;
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;
}

* {
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  margin: 0;
  padding: 0;
  background-color: var(--color-background);
  color: var(--color-text);
  line-height: 1.5;
}

#app {
  min-height: 100vh;
}

/* DNR Component Styles */
.dnr-page {
  padding: var(--spacing-md);
}

.dnr-page-title {
  margin: 0 0 var(--spacing-md) 0;
  font-size: 1.5rem;
}

.dnr-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.dnr-card-title {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: 1.25rem;
}

.dnr-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.2s;
}

.dnr-button:hover {
  background: var(--color-background);
}

.dnr-button-primary {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.dnr-button-primary:hover {
  background: #0056b3;
}

.dnr-input {
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 1rem;
  width: 100%;
}

.dnr-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.dnr-data-table {
  width: 100%;
  border-collapse: collapse;
}

.dnr-data-table th,
.dnr-data-table td {
  padding: var(--spacing-sm);
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.dnr-data-table tr:hover {
  background: var(--color-surface);
}

.dnr-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.dnr-stack {
  display: flex;
}
'''


# =============================================================================
# Vite Project Generator
# =============================================================================


class ViteGenerator:
    """
    Generates a Vite-bundled application from UISpec.

    Creates a complete project with:
    - ES module runtime
    - Vite configuration
    - Package.json
    - Source files
    """

    def __init__(self, spec: UISpec):
        """
        Initialize the generator.

        Args:
            spec: UI specification
        """
        self.spec = spec

    def generate_package_json(self) -> str:
        """Generate package.json content."""
        name = self.spec.name or "dnr-app"
        # Sanitize name for npm
        name = name.lower().replace(" ", "-").replace("_", "-")
        return PACKAGE_JSON_TEMPLATE.format(name=name)

    def generate_vite_config(self) -> str:
        """Generate vite.config.js content."""
        return VITE_CONFIG_JS

    def generate_index_html(self) -> str:
        """Generate index.html content."""
        title = self.spec.name or "DNR UI"
        return INDEX_HTML_TEMPLATE.format(title=title)

    def generate_main_js(self) -> str:
        """Generate main.js entry point."""
        return MAIN_JS_TEMPLATE

    def generate_spec_json(self) -> str:
        """Generate UI spec as JSON."""
        return json.dumps(self.spec.model_dump(by_alias=True), indent=2)

    def write_to_directory(
        self,
        output_dir: str | Path,
    ) -> list[Path]:
        """
        Write complete Vite project to a directory.

        Args:
            output_dir: Output directory path

        Returns:
            List of created file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[Path] = []

        # Write root files
        package_json = output_dir / "package.json"
        package_json.write_text(self.generate_package_json())
        created_files.append(package_json)

        vite_config = output_dir / "vite.config.js"
        vite_config.write_text(self.generate_vite_config())
        created_files.append(vite_config)

        # Create src directory
        src_dir = output_dir / "src"
        src_dir.mkdir(exist_ok=True)

        # Write HTML
        index_html = src_dir / "index.html"
        index_html.write_text(self.generate_index_html())
        created_files.append(index_html)

        # Write main.js
        main_js = src_dir / "main.js"
        main_js.write_text(self.generate_main_js())
        created_files.append(main_js)

        # Write UI spec
        spec_json = src_dir / "ui-spec.json"
        spec_json.write_text(self.generate_spec_json())
        created_files.append(spec_json)

        # Create styles directory
        styles_dir = src_dir / "styles"
        styles_dir.mkdir(exist_ok=True)

        # Write CSS
        css_file = styles_dir / "dnr.css"
        css_file.write_text(DNR_CSS)
        created_files.append(css_file)

        # Create DNR runtime directory
        dnr_dir = src_dir / "dnr"
        dnr_dir.mkdir(exist_ok=True)

        # Write ES module runtime files
        runtime_files = {
            "signals.js": SIGNALS_JS,
            "state.js": STATE_JS,
            "dom.js": DOM_JS,
            "bindings.js": BINDINGS_JS,
            "components.js": COMPONENTS_JS,
            "renderer.js": RENDERER_JS,
            "theme.js": THEME_JS,
            "actions.js": ACTIONS_JS,
            "app.js": APP_JS,
            "index.js": INDEX_JS,
        }

        for filename, content in runtime_files.items():
            file_path = dnr_dir / filename
            file_path.write_text(content)
            created_files.append(file_path)

        return created_files

    def write_runtime_only(
        self,
        output_dir: str | Path,
    ) -> list[Path]:
        """
        Write only the ES module runtime files (for integration into existing projects).

        Args:
            output_dir: Output directory path

        Returns:
            List of created file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[Path] = []

        runtime_files = {
            "signals.js": SIGNALS_JS,
            "state.js": STATE_JS,
            "dom.js": DOM_JS,
            "bindings.js": BINDINGS_JS,
            "components.js": COMPONENTS_JS,
            "renderer.js": RENDERER_JS,
            "theme.js": THEME_JS,
            "actions.js": ACTIONS_JS,
            "app.js": APP_JS,
            "index.js": INDEX_JS,
        }

        for filename, content in runtime_files.items():
            file_path = output_dir / filename
            file_path.write_text(content)
            created_files.append(file_path)

        return created_files


# =============================================================================
# Convenience Functions
# =============================================================================


def generate_vite_app(spec: UISpec, output_dir: str | Path) -> list[Path]:
    """
    Generate a complete Vite application from UISpec.

    Args:
        spec: UI specification
        output_dir: Output directory

    Returns:
        List of created file paths
    """
    generator = ViteGenerator(spec)
    return generator.write_to_directory(output_dir)


def generate_es_modules(spec: UISpec, output_dir: str | Path) -> list[Path]:
    """
    Generate only the ES module runtime files.

    Args:
        spec: UI specification (not used, but kept for API consistency)
        output_dir: Output directory

    Returns:
        List of created file paths
    """
    generator = ViteGenerator(spec)
    return generator.write_runtime_only(output_dir)
