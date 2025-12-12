/**
 * DNR-UI Application Bootstrap - App initialization and routing
 * Part of the Dazzle Native Runtime
 */

import { registerComponent, getComponent } from './components.js';
import { registerState } from './state.js';
import { applyTheme } from './theme.js';
import { renderViewNode } from './renderer.js';
import { render } from './dom.js';
import { createShell, updateActiveNav, checkAuthState } from './shell.js';

// =============================================================================
// Route Matching
// =============================================================================

/**
 * Match a URL path against a route pattern.
 * Supports :id style params.
 */
function matchRoute(pattern, path) {
  // Normalize paths
  const normalizedPattern = pattern.replace(/\/$/, '') || '/';
  const normalizedPath = path.replace(/\/$/, '') || '/';

  // Split into segments
  const patternParts = normalizedPattern.split('/');
  const pathParts = normalizedPath.split('/');

  if (patternParts.length !== pathParts.length) {
    return null;
  }

  const params = {};
  for (let i = 0; i < patternParts.length; i++) {
    const patternPart = patternParts[i];
    const pathPart = pathParts[i];

    if (patternPart.startsWith(':')) {
      // Param placeholder
      const paramName = patternPart.slice(1);
      params[paramName] = pathPart;
    } else if (patternPart !== pathPart) {
      // Mismatch
      return null;
    }
  }

  return params;
}

/**
 * Find the best matching route for a path.
 */
function findRoute(routes, path) {
  for (const route of routes) {
    const params = matchRoute(route.path, path);
    if (params !== null) {
      return { route, params };
    }
  }
  return null;
}

// =============================================================================
// Application Factory
// =============================================================================

export function createApp(uiSpec) {
  // Register custom components from spec
  (uiSpec.components || []).forEach(comp => {
    if (comp.view && !getComponent(comp.name)) {
      registerComponent(comp.name, (props, _children) => {
        // Initialize component state
        (comp.state || []).forEach(stateSpec => {
          const scope = stateSpec.scope || 'local';
          const path = scope === 'local' ? `${comp.name}_${stateSpec.name}` : stateSpec.name;
          registerState(scope, path, stateSpec.initial, stateSpec.persistent);
        });

        // Build dazzle semantic context from component metadata
        const dazzleContext = {
          view: comp.view_name || comp.viewName || comp.name,
          entity: comp.entity_name || comp.entityName,
          ...props.dazzle,  // Allow props to override
        };

        // Build context
        const context = {
          componentId: comp.name,
          props,
          slots: {},
          dazzle: dazzleContext,
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

  let currentWorkspace = null;
  let appContainer = null;
  let shellContainer = null;

  // Check if path matches a static page
  function findStaticPage(path) {
    const pages = uiSpec.shell?.pages || [];
    return pages.find(page => page.route === path);
  }

  // Render a static page
  async function renderStaticPage(page) {
    const StaticPageFn = getComponent('StaticPage');
    if (!StaticPageFn) {
      console.warn('StaticPage component not found');
      return false;
    }

    // Show loading state
    render(appContainer, () => StaticPageFn({ loading: true }, []));

    try {
      // Fetch page content from backend
      const response = await fetch(`/pages${page.route}`);
      if (!response.ok) {
        throw new Error(`Failed to load page: ${response.status}`);
      }
      const data = await response.json();

      // Render with content
      render(appContainer, () => StaticPageFn({
        title: data.title || page.title,
        content: data.content
      }, []));

      return true;
    } catch (error) {
      console.error('Error loading static page:', error);
      render(appContainer, () => StaticPageFn({
        error: `Failed to load page: ${error.message}`
      }, []));
      return false;
    }
  }

  // Render function for a given path
  function renderRoute(path) {
    if (!appContainer) return;

    // Update nav active state
    if (shellContainer) {
      updateActiveNav(shellContainer, path);
    }

    // Check for static page first
    const staticPage = findStaticPage(path);
    if (staticPage) {
      renderStaticPage(staticPage);
      return true;
    }

    // Then check workspace routes
    if (!currentWorkspace) return false;

    const match = findRoute(currentWorkspace.routes, path);
    if (match) {
      const ComponentFn = getComponent(match.route.component);
      if (ComponentFn) {
        // Pass route params as props
        render(appContainer, () => ComponentFn({ routeParams: match.params }, []));
        return true;
      } else {
        console.warn(`Component "${match.route.component}" not found`);
      }
    }

    // Fallback to default route
    const defaultRoute = currentWorkspace.routes && currentWorkspace.routes[0];
    if (defaultRoute) {
      const ComponentFn = getComponent(defaultRoute.component);
      if (ComponentFn) {
        render(appContainer, () => ComponentFn({}, []));
        return true;
      }
    }

    return false;
  }

  return {
    mount(container, workspaceName) {
      const workspace = (uiSpec.workspaces || []).find(w => w.name === workspaceName);
      if (!workspace) {
        console.error(`Workspace "${workspaceName}" not found`);
        return;
      }

      currentWorkspace = workspace;
      shellContainer = container;

      // Create shell and get the main content area
      appContainer = createShell(uiSpec.shell, container);

      // Check authentication state and update UI
      checkAuthState();

      // Initialize workspace state
      (workspace.state || []).forEach(stateSpec => {
        registerState('workspace', stateSpec.name, stateSpec.initial, stateSpec.persistent);
      });

      // Listen for navigation events
      window.addEventListener('dnr-navigate', (event) => {
        const url = event.detail && event.detail.url;
        if (url) {
          const path = new URL(url, window.location.origin).pathname;
          window.history.pushState({}, '', url);
          renderRoute(path);
        }
      });

      // Listen for browser back/forward
      window.addEventListener('popstate', () => {
        renderRoute(window.location.pathname);
      });

      // Render initial route based on current URL
      renderRoute(window.location.pathname);
    },

    navigate(route) {
      window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url: route } }));
    },

    // Re-export commonly needed functions
    getComponent,
    registerComponent,
    applyTheme
  };
}
