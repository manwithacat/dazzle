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
// Semantic Attributes (data-dazzle-*)
// =============================================================================

/**
 * Add Dazzle semantic attributes to an element.
 * These attributes enable stack-agnostic E2E testing.
 *
 * @param {HTMLElement} element - Element to add attributes to
 * @param {Object} attrs - Semantic attribute values
 * @returns {HTMLElement} The element with attributes added
 *
 * @example
 * withDazzleAttrs(button, {
 *   action: 'Task.create',
 *   actionRole: 'primary'
 * });
 * // Adds: data-dazzle-action="Task.create" data-dazzle-action-role="primary"
 */
export function withDazzleAttrs(element, attrs) {
  if (!attrs) return element;

  const attrMap = {
    // Views
    view: 'view',
    // Entity context
    entity: 'entity',
    entityId: 'entity-id',
    // Fields
    field: 'field',
    fieldType: 'field-type',
    fieldGroup: 'field-group',
    required: 'required',
    label: 'label',
    // Actions
    action: 'action',
    actionRole: 'action-role',
    // Messages
    message: 'message',
    messageKind: 'message-kind',
    // Navigation
    nav: 'nav',
    navTarget: 'nav-target',
    navParams: 'nav-params',
    // Tables
    table: 'table',
    column: 'column',
    row: 'row',
    cell: 'cell',
    // Forms
    form: 'form',
    formMode: 'form-mode',
    // Dialogs
    dialog: 'dialog',
    dialogOpen: 'dialog-open',
    dialogTitle: 'dialog-title',
    dialogContent: 'dialog-content',
    dialogActions: 'dialog-actions',
    // Loading
    loading: 'loading',
    // Breadcrumb
    breadcrumb: 'breadcrumb',
    breadcrumbCurrent: 'breadcrumb-current'
  };

  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null && value !== false) {
      const attrName = attrMap[key] || key;
      const attrValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
      element.setAttribute(`data-dazzle-${attrName}`, attrValue);
    }
  }

  return element;
}

/**
 * Create an element with Dazzle semantic attributes.
 * Convenience wrapper around createElement + withDazzleAttrs.
 *
 * @param {string} tag - HTML tag name
 * @param {Object} props - Element props (including dazzle attrs under 'dazzle' key)
 * @param {Array} children - Child elements
 * @returns {HTMLElement}
 *
 * @example
 * createDazzleElement('button', {
 *   className: 'btn-primary',
 *   onClick: handleClick,
 *   dazzle: { action: 'Task.create', actionRole: 'primary' }
 * }, ['Create Task']);
 */
export function createDazzleElement(tag, props = {}, children = []) {
  const { dazzle, ...restProps } = props;
  const element = createElement(tag, restProps, children);
  if (dazzle) {
    withDazzleAttrs(element, dazzle);
  }
  return element;
}

// =============================================================================
// Path Utilities
// =============================================================================

export function getByPath(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((o, p) => o && o[p], obj);
}
