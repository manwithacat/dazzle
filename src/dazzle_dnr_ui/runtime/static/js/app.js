/**
 * DNR-UI Application Bootstrap - App initialization and routing
 * Part of the Dazzle Native Runtime
 */

import { registerComponent, getComponent } from './components.js';
import { registerState } from './state.js';
import { applyTheme } from './theme.js';
import { renderViewNode } from './renderer.js';
import { render } from './dom.js';

// =============================================================================
// Application Factory
// =============================================================================

export function createApp(uiSpec) {
  // Register custom components from spec
  (uiSpec.components || []).forEach(comp => {
    if (comp.view && !getComponent(comp.name)) {
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

    // Re-export commonly needed functions
    getComponent,
    registerComponent,
    applyTheme
  };
}
