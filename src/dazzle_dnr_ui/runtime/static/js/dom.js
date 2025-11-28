/**
 * DNR-UI DOM Helpers - Element creation and rendering
 * Part of the Dazzle Native Runtime
 */

import { createEffect } from './signals.js';

// =============================================================================
// Element Creation
// =============================================================================

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

// =============================================================================
// Rendering
// =============================================================================

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

// =============================================================================
// Path Utilities
// =============================================================================

export function getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((o, p) => o && o[p], obj);
}
