/**
 * DNR-UI Shell - Application chrome rendering (nav, header, footer)
 * Part of the Dazzle Native Runtime
 *
 * The shell wraps workspace content with:
 * - Navigation (sidebar, topbar, or tabs)
 * - Header with optional auth UI
 * - Footer with links and "Made with Dazzle"
 */

// =============================================================================
// Shell Rendering
// =============================================================================

/**
 * Render navigation items as HTML.
 * @param {Array} items - Navigation items from shell.nav.items
 * @param {string} currentPath - Current URL path for active state
 */
function renderNavItems(items, currentPath) {
  return items.map(item => {
    const isActive = currentPath === item.route ||
                     (item.route !== '/' && currentPath.startsWith(item.route));
    const activeClass = isActive ? 'active' : '';
    return `
      <li>
        <a href="${item.route}"
           class="${activeClass}"
           data-dnr-nav-item
           data-workspace="${item.workspace || ''}">
          ${item.icon ? `<span class="icon">${item.icon}</span>` : ''}
          ${item.label}
        </a>
      </li>
    `;
  }).join('');
}

/**
 * Render sidebar navigation.
 * Uses DaisyUI drawer component.
 */
function renderSidebarNav(shell, currentPath) {
  const { nav, header } = shell;
  const navItems = renderNavItems(nav.items || [], currentPath);

  return `
    <div class="drawer lg:drawer-open">
      <input id="dz-drawer" type="checkbox" class="drawer-toggle" />

      <div class="drawer-content flex flex-col">
        <!-- Navbar for mobile -->
        <div class="navbar bg-base-100 lg:hidden border-b border-base-300">
          <div class="flex-none">
            <label for="dz-drawer" class="btn btn-square btn-ghost drawer-button">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="inline-block w-5 h-5 stroke-current">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path>
              </svg>
            </label>
          </div>
          <div class="flex-1">
            <span class="text-xl font-semibold">${nav.brand || ''}</span>
          </div>
          ${header.show_auth ? renderAuthButton() : ''}
        </div>

        <!-- Main content area -->
        <main class="dz-app__main flex-1" id="dz-main-content">
          <!-- Workspace content renders here -->
        </main>

        ${renderFooter(shell)}
      </div>

      <div class="drawer-side z-40">
        <label for="dz-drawer" class="drawer-overlay"></label>
        <aside class="bg-base-200 w-64 min-h-full flex flex-col">
          <!-- Brand -->
          <div class="p-4 border-b border-base-300">
            <a href="/" class="text-xl font-bold">${nav.brand || 'App'}</a>
          </div>

          <!-- Navigation -->
          <ul class="menu p-4 flex-1">
            ${navItems}
          </ul>

          <!-- Desktop auth in sidebar footer -->
          ${header.show_auth ? `
            <div class="p-4 border-t border-base-300 hidden lg:block">
              ${renderAuthSection()}
            </div>
          ` : ''}
        </aside>
      </div>
    </div>
  `;
}

/**
 * Render topbar navigation.
 * Uses DaisyUI navbar component.
 */
function renderTopbarNav(shell, currentPath) {
  const { nav, header } = shell;
  const navItems = nav.items || [];

  return `
    <div class="flex flex-col min-h-screen">
      <nav class="navbar bg-base-100 border-b border-base-300 px-4">
        <!-- Brand -->
        <div class="flex-1">
          <a href="/" class="text-xl font-bold">${nav.brand || 'App'}</a>
        </div>

        <!-- Desktop nav -->
        <div class="hidden md:flex flex-none">
          <ul class="menu menu-horizontal px-1">
            ${navItems.map(item => {
              const isActive = currentPath === item.route;
              return `
                <li>
                  <a href="${item.route}"
                     class="${isActive ? 'active' : ''}"
                     data-dnr-nav-item>
                    ${item.label}
                  </a>
                </li>
              `;
            }).join('')}
          </ul>
        </div>

        ${header.show_auth ? renderAuthButton() : ''}

        <!-- Mobile menu button -->
        <div class="dropdown dropdown-end md:hidden">
          <label tabindex="0" class="btn btn-ghost">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" />
            </svg>
          </label>
          <ul tabindex="0" class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-100 rounded-box w-52">
            ${navItems.map(item => `
              <li><a href="${item.route}">${item.label}</a></li>
            `).join('')}
          </ul>
        </div>
      </nav>

      <!-- Main content -->
      <main class="dz-app__main flex-1" id="dz-main-content">
        <!-- Workspace content renders here -->
      </main>

      ${renderFooter(shell)}
    </div>
  `;
}

/**
 * Render tab-style navigation.
 * Uses DaisyUI tabs component.
 */
function renderTabsNav(shell, currentPath) {
  const { nav, header } = shell;
  const navItems = nav.items || [];

  return `
    <div class="flex flex-col min-h-screen">
      <!-- Header with brand and auth -->
      <header class="bg-base-100 border-b border-base-300 px-4 py-3 flex items-center justify-between">
        <a href="/" class="text-xl font-bold">${nav.brand || 'App'}</a>
        ${header.show_auth ? renderAuthButton() : ''}
      </header>

      <!-- Tabs navigation -->
      <div class="bg-base-100 border-b border-base-300">
        <div role="tablist" class="tabs tabs-bordered max-w-4xl mx-auto">
          ${navItems.map(item => {
            const isActive = currentPath === item.route;
            return `
              <a href="${item.route}"
                 role="tab"
                 class="tab ${isActive ? 'tab-active' : ''}"
                 data-dnr-nav-item>
                ${item.label}
              </a>
            `;
          }).join('')}
        </div>
      </div>

      <!-- Main content -->
      <main class="dz-app__main flex-1" id="dz-main-content">
        <!-- Workspace content renders here -->
      </main>

      ${renderFooter(shell)}
    </div>
  `;
}

/**
 * Render auth button (login/logout) for navbar.
 * Shows login button when not authenticated, user menu when authenticated.
 */
function renderAuthButton() {
  return `
    <div class="flex-none" id="dz-auth-button">
      <!-- Loading state while checking auth -->
      <button class="btn btn-ghost btn-sm loading" disabled></button>
    </div>
  `;
}

/**
 * Render auth section for sidebar.
 * Shows guest state or logged-in user info.
 */
function renderAuthSection() {
  return `
    <div id="dz-auth-section" class="flex items-center gap-2">
      <!-- Loading state while checking auth -->
      <div class="loading loading-spinner loading-sm"></div>
      <span class="text-sm">Loading...</span>
    </div>
  `;
}

/**
 * Update auth UI based on current auth state.
 * Called after checking /api/auth/me endpoint.
 *
 * Uses semantic attributes for E2E testing:
 * - data-dazzle-auth-user: Present on user indicator when logged in
 * - data-dazzle-auth-action="login": On login button
 * - data-dazzle-auth-action="logout": On logout button
 * - data-dazzle-persona: User's persona/role when available
 */
function updateAuthUI(user) {
  const authButton = document.getElementById('dz-auth-button');
  const authSection = document.getElementById('dz-auth-section');

  if (user && user.is_authenticated) {
    // Logged in state
    const personaAttr = user.persona ? `data-dazzle-persona="${user.persona}"` : '';

    if (authButton) {
      authButton.innerHTML = `
        <div class="dropdown dropdown-end" data-dazzle-auth-user ${personaAttr}>
          <label tabindex="0" class="btn btn-ghost btn-circle avatar placeholder">
            <div class="bg-primary text-primary-content rounded-full w-8">
              <span class="text-sm">${(user.display_name || user.email || 'U')[0].toUpperCase()}</span>
            </div>
          </label>
          <ul tabindex="0" class="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-100 rounded-box w-52">
            <li class="menu-title"><span>${user.email}</span></li>
            <li><a href="#" data-dnr-logout data-dazzle-auth-action="logout">Logout</a></li>
          </ul>
        </div>
      `;
    }
    if (authSection) {
      authSection.innerHTML = `
        <div class="avatar placeholder" data-dazzle-auth-user ${personaAttr}>
          <div class="bg-primary text-primary-content rounded-full w-8">
            <span class="text-sm">${(user.display_name || user.email || 'U')[0].toUpperCase()}</span>
          </div>
        </div>
        <div class="flex flex-col">
          <span class="text-sm font-medium">${user.display_name || user.email}</span>
          <a href="#" data-dnr-logout data-dazzle-auth-action="logout" class="text-xs link link-hover">Logout</a>
        </div>
      `;
    }
  } else {
    // Guest state - show login button
    if (authButton) {
      authButton.innerHTML = `
        <button class="btn btn-ghost btn-sm" data-dnr-login data-dazzle-auth-action="login">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
          </svg>
          Login
        </button>
      `;
    }
    if (authSection) {
      authSection.innerHTML = `
        <div class="avatar placeholder">
          <div class="bg-neutral text-neutral-content rounded-full w-8">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
        </div>
        <button class="btn btn-sm btn-primary" data-dnr-login data-dazzle-auth-action="login">Login</button>
      `;
    }
  }

  // Set up logout handlers
  document.querySelectorAll('[data-dnr-logout]').forEach(el => {
    el.addEventListener('click', handleLogout);
  });

  // Set up login handlers
  document.querySelectorAll('[data-dnr-login]').forEach(el => {
    el.addEventListener('click', showLoginModal);
  });
}

/**
 * Check current auth state and update UI.
 */
async function checkAuthState() {
  try {
    const response = await fetch('/api/auth/me', { credentials: 'include' });
    if (response.ok) {
      const user = await response.json();
      updateAuthUI(user);
      window.dnrAuthUser = user;
    } else {
      updateAuthUI(null);
      window.dnrAuthUser = null;
    }
  } catch (error) {
    console.log('[DNR] Auth check failed (auth may not be enabled):', error.message);
    updateAuthUI(null);
    window.dnrAuthUser = null;
  }
}

/**
 * Handle logout action.
 */
async function handleLogout(e) {
  e.preventDefault();
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    window.dnrAuthUser = null;
    updateAuthUI(null);
    // Optionally redirect to home
    window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url: '/' } }));
  } catch (error) {
    console.error('[DNR] Logout failed:', error);
  }
}

/**
 * Show login modal.
 */
function showLoginModal(e) {
  if (e) e.preventDefault();

  // Remove any existing modal
  const existing = document.getElementById('dz-auth-modal');
  if (existing) existing.remove();

  const modal = document.createElement('dialog');
  modal.id = 'dz-auth-modal';
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-box">
      <form method="dialog">
        <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2">✕</button>
      </form>
      <h3 class="font-bold text-lg mb-4" id="dz-auth-modal-title">Login</h3>

      <div id="dz-auth-error" class="alert alert-error mb-4 hidden">
        <span></span>
      </div>

      <form id="dz-auth-form" class="space-y-4">
        <div class="form-control">
          <label class="label"><span class="label-text">Email</span></label>
          <input type="email" name="email" class="input input-bordered" required />
        </div>
        <div class="form-control">
          <label class="label"><span class="label-text">Password</span></label>
          <input type="password" name="password" class="input input-bordered" required />
        </div>
        <div class="form-control hidden" id="dz-auth-name-field">
          <label class="label"><span class="label-text">Display Name</span></label>
          <input type="text" name="display_name" class="input input-bordered" />
        </div>
        <div class="flex gap-2">
          <button type="submit" class="btn btn-primary flex-1" id="dz-auth-submit">Login</button>
        </div>
        <div class="text-center">
          <a href="#" class="link text-sm" id="dz-auth-toggle" data-dazzle-auth-toggle="register">Don't have an account? Register</a>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  `;

  document.body.appendChild(modal);
  modal.showModal();

  // Toggle between login and register
  let isRegister = false;
  const toggle = modal.querySelector('#dz-auth-toggle');
  const title = modal.querySelector('#dz-auth-modal-title');
  const submit = modal.querySelector('#dz-auth-submit');
  const nameField = modal.querySelector('#dz-auth-name-field');

  toggle.addEventListener('click', (e) => {
    e.preventDefault();
    isRegister = !isRegister;
    title.textContent = isRegister ? 'Register' : 'Login';
    submit.textContent = isRegister ? 'Register' : 'Login';
    toggle.textContent = isRegister ? 'Already have an account? Login' : "Don't have an account? Register";
    toggle.setAttribute('data-dazzle-auth-toggle', isRegister ? 'login' : 'register');
    nameField.classList.toggle('hidden', !isRegister);
  });

  // Handle form submission
  const form = modal.querySelector('#dz-auth-form');
  const errorDiv = modal.querySelector('#dz-auth-error');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorDiv.classList.add('hidden');

    const formData = new FormData(form);
    const data = {
      email: formData.get('email'),
      password: formData.get('password'),
    };
    if (isRegister) {
      data.display_name = formData.get('display_name') || undefined;
    }

    try {
      const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(data),
      });

      if (response.ok) {
        const result = await response.json();
        window.dnrAuthUser = result.user;
        updateAuthUI(result.user);
        modal.close();
      } else {
        const error = await response.json();
        errorDiv.querySelector('span').textContent = error.detail || 'Authentication failed';
        errorDiv.classList.remove('hidden');
      }
    } catch (err) {
      console.error('Login error:', err);
      errorDiv.querySelector('span').textContent = 'Network error. Please try again.';
      errorDiv.classList.remove('hidden');
    }
  });
}

// Export for use in app.js
export { checkAuthState, updateAuthUI, showLoginModal };

/**
 * Render footer.
 * Uses DaisyUI footer component.
 */
function renderFooter(shell) {
  const { footer } = shell;
  if (!footer) return '';

  const links = footer.links || [];
  const poweredBy = footer.powered_by !== false; // Default true

  return `
    <footer class="footer footer-center p-6 bg-base-200 text-base-content border-t border-base-300">
      ${footer.copyright ? `<p class="text-sm">${footer.copyright}</p>` : ''}

      ${links.length > 0 ? `
        <nav class="flex gap-4">
          ${links.map(link => {
            // Internal links (starting with /) use data-dnr-nav-item for SPA navigation
            const isInternal = link.href.startsWith('/');
            return `
              <a href="${link.href}"
                 class="link link-hover text-sm"
                 ${isInternal ? 'data-dnr-nav-item data-static-page="true"' : 'target="_blank" rel="noopener"'}>
                ${link.label}
              </a>
            `;
          }).join('')}
        </nav>
      ` : ''}

      ${poweredBy ? `
        <aside class="mt-2">
          <a href="https://github.com/manwithacat/dazzle"
             target="_blank"
             rel="noopener noreferrer"
             class="link link-hover text-xs opacity-60 flex items-center gap-1">
            Made with Dazzle
          </a>
        </aside>
      ` : ''}
    </footer>
  `;
}

/**
 * Render minimal shell (no nav, just header/footer).
 */
function renderMinimalShell(shell) {
  const { header } = shell;

  return `
    <div class="flex flex-col min-h-screen">
      ${header.title ? `
        <header class="bg-base-100 border-b border-base-300 px-4 py-3 flex items-center justify-between">
          <span class="text-xl font-bold">${header.title}</span>
          ${header.show_auth ? renderAuthButton() : ''}
        </header>
      ` : ''}

      <main class="dz-app__main flex-1" id="dz-main-content">
        <!-- Workspace content renders here -->
      </main>

      ${renderFooter(shell)}
    </div>
  `;
}

// =============================================================================
// Shell API
// =============================================================================

/**
 * Create and render the application shell.
 * @param {Object} shell - Shell spec from UISpec
 * @param {HTMLElement} container - Container element to render into
 * @returns {HTMLElement} The main content element where workspace should be mounted
 */
export function createShell(shell, container) {
  if (!shell) {
    // No shell config, return container as-is
    container.id = 'dz-main-content';
    container.classList.add('dz-app__main');
    return container;
  }

  const currentPath = window.location.pathname;
  const navStyle = shell.nav?.style || 'sidebar';
  const layout = shell.layout || 'app-shell';

  let shellHtml;

  if (layout === 'minimal') {
    shellHtml = renderMinimalShell(shell);
  } else {
    switch (navStyle) {
      case 'topbar':
        shellHtml = renderTopbarNav(shell, currentPath);
        break;
      case 'tabs':
        shellHtml = renderTabsNav(shell, currentPath);
        break;
      case 'sidebar':
      default:
        shellHtml = renderSidebarNav(shell, currentPath);
        break;
    }
  }

  container.innerHTML = shellHtml;

  // Set up navigation link handlers
  setupNavigation(container);

  // Return the main content element
  return container.querySelector('#dz-main-content') || container;
}

/**
 * Set up click handlers for navigation links.
 */
function setupNavigation(container) {
  container.addEventListener('click', (e) => {
    const link = e.target.closest('a[data-dnr-nav-item]');
    if (link) {
      e.preventDefault();
      const href = link.getAttribute('href');
      window.dispatchEvent(new CustomEvent('dnr-navigate', {
        detail: { url: href }
      }));

      // Update active state
      container.querySelectorAll('[data-dnr-nav-item]').forEach(el => {
        el.classList.remove('active', 'tab-active');
      });
      link.classList.add('active');
      if (link.role === 'tab') {
        link.classList.add('tab-active');
      }

      // Close mobile drawer if open
      const drawer = container.querySelector('#dz-drawer');
      if (drawer) drawer.checked = false;
    }
  });
}

/**
 * Update navigation active state for a new path.
 */
export function updateActiveNav(container, path) {
  container.querySelectorAll('[data-dnr-nav-item]').forEach(link => {
    const href = link.getAttribute('href');
    const isActive = path === href || (href !== '/' && path.startsWith(href));
    link.classList.toggle('active', isActive);
    if (link.role === 'tab') {
      link.classList.toggle('tab-active', isActive);
    }
  });
}
