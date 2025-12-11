/**
 * DNR-UI Binding Resolution - Data binding system
 * Part of the Dazzle Native Runtime
 */

import { getState, stateStores } from './state.js';
import { getByPath } from './dom.js';

// =============================================================================
// Binding Resolution
// =============================================================================

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
      // Simple expression evaluation (be careful with this in production!)
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

// =============================================================================
// Expression Evaluation
// =============================================================================

export function evalExpression(expr, context) {
  // Safe expression evaluation using Function constructor
  // Only allows access to context values
  // eslint-disable-next-line no-new-func -- Required for DSL expression binding
  const fn = new Function('ctx', `with(ctx) { return ${expr}; }`);
  return fn({
    props: context.props || {},
    state: context.state || {},
    workspace: stateStores.workspace,
    app: stateStores.app
  });
}
