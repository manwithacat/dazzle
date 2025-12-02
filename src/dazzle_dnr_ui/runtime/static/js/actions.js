// @ts-check
/**
 * DNR-UI Actions & Effects - Action execution system
 * Part of the Dazzle Native Runtime
 *
 * @module actions
 */

import { batch } from './signals.js';
import { setState, updateState, setGlobalLoading, setGlobalError } from './state.js';
import { resolveBinding } from './bindings.js';
import { apiClient } from './api-client.js';
import { showToast } from './toast.js';

/** @type {((name: string, payload: any) => void) | null} */
let actionLogger = null;

/**
 * Set a function to log action dispatches (used by devtools).
 * @param {(name: string, payload: any) => void} logger
 */
export function setActionLogger(logger) {
  actionLogger = logger;
}

// =============================================================================
// Action Registry
// =============================================================================

const actionRegistry = new Map();

export function registerAction(name, handler) {
  actionRegistry.set(name, handler);
}

/**
 * Dispatch an action by name.
 * @param {string} actionName - Name of the action to dispatch
 * @param {Object} [payload={}] - Action payload
 * @returns {any}
 */
export function dispatch(actionName, payload = {}) {
  // Log to devtools if available
  if (actionLogger) {
    actionLogger(actionName, payload);
  }

  const handler = actionRegistry.get(actionName);
  if (handler) {
    return handler(payload);
  }
  console.warn(`Action not found: ${actionName}`);
}

export function hasAction(name) {
  return actionRegistry.has(name);
}

// =============================================================================
// Action Execution
// =============================================================================

export async function executeAction(action, context) {
  if (!action) return;

  const actionName = typeof action === 'string' ? action : action.name;

  // Check for registered actions first
  if (actionRegistry.has(actionName)) {
    return dispatch(actionName, context.payload || context.data || {});
  }

  // Apply state transitions with batch for performance
  if (action.transitions && action.transitions.length > 0) {
    batch(() => {
      action.transitions.forEach(transition => {
        const scope = transition.scope || 'local';
        const targetState = transition.target_state || transition.targetState;
        const path = scope === 'local' ?
          `${context.componentId}_${targetState}` : targetState;

        // Handle patch operations
        const update = transition.update;
        if (update && update.op) {
          applyPatch(scope, path, update, context);
        } else {
          // Simple set
          const value = resolveBinding(transition.value || update, context);
          setState(scope, path, value);
        }
      });
    });
  }

  // Execute effect
  if (action.effect) {
    await executeEffect(action.effect, context);
  }
}

// =============================================================================
// Patch Operations
// =============================================================================

export function applyPatch(scope, path, patch, context) {
  const value = resolveBinding(patch.value, context);

  switch (patch.op) {
    case 'set':
      setState(scope, path, value);
      break;

    case 'merge':
      updateState(scope, path, current => ({ ...current, ...value }));
      break;

    case 'append':
      updateState(scope, path, current => Array.isArray(current) ? [...current, value] : [value]);
      break;

    case 'remove':
      updateState(scope, path, current => {
        if (Array.isArray(current)) {
          return current.filter(item => {
            if (typeof value === 'function') return !value(item);
            if (typeof value === 'object' && value.id) return item.id !== value.id;
            return item !== value;
          });
        }
        return current;
      });
      break;

    case 'delete':
      setState(scope, path, undefined);
      break;
  }
}

// =============================================================================
// Effect Execution
// =============================================================================

export async function executeEffect(effect, context) {
  if (!effect) return;

  switch (effect.kind) {
    case 'fetch': {
      const service = effect.backend_service || effect.backendService;
      const method = effect.method || 'GET';
      const inputs = {};

      // Resolve input bindings
      Object.entries(effect.inputs || {}).forEach(([key, binding]) => {
        inputs[key] = resolveBinding(binding, context);
      });

      setGlobalLoading(true);
      setGlobalError(null);

      try {
        let result;
        const entity = service.replace(/_service$/, 's');

        // Map to appropriate API call based on method
        if (method === 'GET' || effect.operation === 'list') {
          result = await apiClient.list(entity, inputs);
        } else if (effect.operation === 'read' && inputs.id) {
          result = await apiClient.read(entity, inputs.id);
        } else if (method === 'POST' || effect.operation === 'create') {
          result = await apiClient.create(entity, inputs);
        } else if (method === 'PUT' || effect.operation === 'update') {
          result = await apiClient.update(entity, inputs.id, inputs);
        } else if (method === 'DELETE' || effect.operation === 'delete') {
          result = await apiClient.remove(entity, inputs.id);
        } else {
          // Generic fetch
          result = await apiClient.request(method, `/${service}`, inputs);
        }

        // Handle success
        if (effect.on_success || effect.onSuccess) {
          const successAction = context.getAction ?
            context.getAction(effect.on_success || effect.onSuccess) :
            { name: effect.on_success || effect.onSuccess };

          if (successAction) {
            await executeAction(successAction, { ...context, data: result, result });
          }
        }

        return result;
      } catch (error) {
        setGlobalError(error);
        console.error('Fetch effect failed:', error);

        // Handle error
        if (effect.on_error || effect.onError) {
          const errorAction = context.getAction ?
            context.getAction(effect.on_error || effect.onError) :
            { name: effect.on_error || effect.onError };

          if (errorAction) {
            await executeAction(errorAction, { ...context, error });
          }
        } else {
          // Default error handling
          showToast(error.message || 'An error occurred', { variant: 'error' });
        }
      } finally {
        setGlobalLoading(false);
      }
      break;
    }

    case 'navigate': {
      const route = effect.route;
      const params = {};
      Object.entries(effect.params || {}).forEach(([key, binding]) => {
        params[key] = resolveBinding(binding, context);
      });

      // Replace route params
      let url = route;
      Object.entries(params).forEach(([key, value]) => {
        url = url.replace(`{${key}}`, encodeURIComponent(value));
        url = url.replace(`:${key}`, encodeURIComponent(value));
      });

      window.history.pushState({ params }, '', url);
      window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url, params } }));
      break;
    }

    case 'log': {
      const message = resolveBinding(effect.message, context);
      const level = effect.level || 'info';
      console[level](message);
      break;
    }

    case 'toast': {
      const message = resolveBinding(effect.message, context);
      showToast(message, {
        variant: effect.variant || 'info',
        duration: effect.duration || 3000
      });
      break;
    }

    case 'custom': {
      const handler = actionRegistry.get(`effect:${effect.name}`);
      if (handler) {
        await handler(effect.config, context);
      } else {
        console.warn(`Custom effect not found: ${effect.name}`);
      }
      break;
    }
  }
}

// =============================================================================
// Built-in Actions
// =============================================================================

// Pure actions (state only, no side effects)
registerAction('filter', ({ items, predicate, target }) => {
  if (!items || !predicate) return items;
  const filtered = items.filter(predicate);
  if (target) setState('workspace', target, filtered);
  return filtered;
});

registerAction('sort', ({ items, key, direction = 'asc', target }) => {
  if (!items || !key) return items;
  const sorted = [...items].sort((a, b) => {
    const aVal = a[key];
    const bVal = b[key];
    const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return direction === 'desc' ? -cmp : cmp;
  });
  if (target) setState('workspace', target, sorted);
  return sorted;
});

registerAction('select', ({ item, target }) => {
  if (target) setState('workspace', target, item);
  return item;
});

registerAction('toggle', ({ path, scope = 'workspace' }) => {
  updateState(scope, path, current => !current);
});

registerAction('reset', ({ path, scope = 'workspace', initial = null }) => {
  setState(scope, path, initial);
});

export { actionRegistry };
