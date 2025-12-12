/**
 * DNR-UI View Renderer - View tree rendering system
 * Part of the Dazzle Native Runtime
 */

import { createElement, getByPath } from './dom.js';
import { resolveBinding } from './bindings.js';
import { getComponent } from './components.js';

// =============================================================================
// View Tree Renderer
// =============================================================================

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

function renderElementNode(node, context) {
  const componentName = node.as || node.as_;
  const ComponentFn = getComponent(componentName);

  // Resolve all props
  const resolvedProps = {};
  Object.entries(node.props || {}).forEach(([key, binding]) => {
    resolvedProps[key] = resolveBinding(binding, context);
  });

  // Pass dazzle semantic context to components
  // This enables the DOM contract (data-dazzle-* attributes)
  // Note: 'view' should only be on the root element, not propagated to children
  if (context.dazzle || node.dazzle) {
    const { view: _contextView, ...contextDazzleWithoutView } = context.dazzle || {};
    resolvedProps.dazzle = {
      ...contextDazzleWithoutView,
      ...node.dazzle, // node.dazzle can override with its own view if explicitly set
    };
  }

  // If component has entityRef, add it to dazzle context
  if (resolvedProps.entityRef || resolvedProps.entity_ref) {
    resolvedProps.dazzle = {
      ...resolvedProps.dazzle,
      entity: resolvedProps.entityRef || resolvedProps.entity_ref,
    };
  }

  // Render children
  const children = (node.children || []).map(child => renderViewNode(child, context)).filter(Boolean);

  if (ComponentFn) {
    return ComponentFn(resolvedProps, children);
  } else {
    // Fall back to HTML element
    return createElement(componentName.toLowerCase(), resolvedProps, children);
  }
}

function renderConditionalNode(node, context) {
  const condition = resolveBinding(node.condition, context);
  if (condition) {
    return renderViewNode(node.then_branch || node.thenBranch, context);
  } else if (node.else_branch || node.elseBranch) {
    return renderViewNode(node.else_branch || node.elseBranch, context);
  }
  return null;
}

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
      child.setAttribute('data-key', getByPath(item, keyPath) || index);
      fragment.appendChild(child);
    }
  });
  return fragment;
}

function renderSlotNode(node, context) {
  const slotContent = context.slots && context.slots[node.name];
  if (slotContent) {
    return renderViewNode(slotContent, context);
  } else if (node.fallback) {
    return renderViewNode(node.fallback, context);
  }
  return null;
}

function renderTextNode(node, context) {
  const content = resolveBinding(node.content, context);
  return document.createTextNode(String(content || ''));
}
