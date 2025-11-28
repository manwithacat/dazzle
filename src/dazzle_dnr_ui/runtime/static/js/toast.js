/**
 * DNR-UI Toast Notifications - User feedback system
 * Part of the Dazzle Native Runtime
 */

import { setNotifications } from './state.js';

// =============================================================================
// Toast Container
// =============================================================================

let toastContainer = null;

function ensureToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'dnr-toast-container';
    toastContainer.style.cssText = `
      position: fixed;
      top: 16px;
      right: 16px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 8px;
      pointer-events: none;
    `;
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

// =============================================================================
// Toast Functions
// =============================================================================

export function showToast(message, options = {}) {
  const {
    variant = 'info',
    duration = 3000,
    action = null
  } = options;

  const container = ensureToastContainer();

  const toast = document.createElement('div');
  toast.className = `dnr-toast dnr-toast-${variant}`;
  toast.style.cssText = `
    padding: 12px 16px;
    border-radius: 4px;
    background: ${variant === 'success' ? '#28a745' :
                 variant === 'error' ? '#dc3545' :
                 variant === 'warning' ? '#ffc107' : '#17a2b8'};
    color: ${variant === 'warning' ? '#212529' : '#fff'};
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 250px;
    max-width: 400px;
    animation: dnr-toast-in 0.3s ease-out;
  `;

  const messageSpan = document.createElement('span');
  messageSpan.textContent = message;
  messageSpan.style.flex = '1';
  toast.appendChild(messageSpan);

  if (action) {
    const actionBtn = document.createElement('button');
    actionBtn.textContent = action.label;
    actionBtn.onclick = action.onClick;
    actionBtn.style.cssText = `
      background: transparent;
      border: 1px solid currentColor;
      color: inherit;
      padding: 4px 8px;
      border-radius: 2px;
      cursor: pointer;
    `;
    toast.appendChild(actionBtn);
  }

  const closeBtn = document.createElement('button');
  closeBtn.textContent = '×';
  closeBtn.style.cssText = `
    background: transparent;
    border: none;
    color: inherit;
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
  `;
  closeBtn.onclick = () => removeToast(toast);
  toast.appendChild(closeBtn);

  container.appendChild(toast);

  // Add notification to state
  const notification = { id: Date.now(), message, variant, timestamp: new Date() };
  setNotifications(prev => [...prev, notification]);

  if (duration > 0) {
    setTimeout(() => removeToast(toast, notification.id), duration);
  }

  return notification.id;
}

export function removeToast(toast, notificationId) {
  toast.style.animation = 'dnr-toast-out 0.2s ease-in forwards';
  setTimeout(() => {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 200);

  if (notificationId) {
    setNotifications(prev => prev.filter(n => n.id !== notificationId));
  }
}

// =============================================================================
// Toast Styles Injection
// =============================================================================

export function injectToastStyles() {
  const toastStyles = document.createElement('style');
  toastStyles.textContent = `
    @keyframes dnr-toast-in {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes dnr-toast-out {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(100%); opacity: 0; }
    }
  `;
  if (typeof document !== 'undefined') {
    document.head.appendChild(toastStyles);
  }
}

// Auto-inject styles on import (browser only)
if (typeof document !== 'undefined') {
  injectToastStyles();
}
