/**
 * DNR-UI Components - Built-in UI primitives
 * Part of the Dazzle Native Runtime
 */

import { createElement } from './dom.js';

// =============================================================================
// Component Registry
// =============================================================================

const componentRegistry = new Map();

export function registerComponent(name, renderFn) {
  componentRegistry.set(name, renderFn);
}

export function getComponent(name) {
  return componentRegistry.get(name);
}

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

  const tbody = createElement('tbody', {}, (data || []).map((row, _idx) =>
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
  // This is a pattern that combines filter inputs with a data table
  return createElement('div', { className: 'dnr-filterable-table' }, [
    createElement('div', { className: 'dnr-filters', style: { marginBottom: '16px' } }, [
      props.filterPlaceholder ?
        createElement('input', {
          type: 'text',
          placeholder: props.filterPlaceholder,
          style: { padding: '8px', width: '200px' }
        }) : null
    ].filter(Boolean)),
    componentRegistry.get('DataTable')(props)
  ]);
});

// Loading indicator
registerComponent('Loading', (props) => {
  const size = props.size || 24;
  return createElement('div', {
    className: 'dnr-loading',
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '8px'
    }
  }, [
    createElement('div', {
      className: 'dnr-spinner',
      style: {
        width: `${size}px`,
        height: `${size}px`,
        border: '2px solid var(--color-border)',
        borderTopColor: 'var(--color-primary)',
        borderRadius: '50%',
        animation: 'dnr-spin 0.8s linear infinite'
      }
    }),
    props.text ? createElement('span', {}, [props.text]) : null
  ].filter(Boolean));
});

// Error display
registerComponent('Error', (props) => {
  return createElement('div', {
    className: 'dnr-error',
    style: {
      padding: 'var(--spacing-md)',
      backgroundColor: '#fef2f2',
      border: '1px solid #fecaca',
      borderRadius: 'var(--radius-md)',
      color: '#991b1b'
    }
  }, [
    createElement('strong', {}, [props.title || 'Error']),
    props.message ? createElement('p', { style: { margin: '8px 0 0' } }, [props.message]) : null,
    props.onRetry ? createElement('button', {
      onClick: props.onRetry,
      style: {
        marginTop: '8px',
        padding: '4px 12px',
        background: '#dc3545',
        color: 'white',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer'
      }
    }, ['Retry']) : null
  ].filter(Boolean));
});

// Empty state
registerComponent('Empty', (props) => {
  return createElement('div', {
    className: 'dnr-empty',
    style: {
      textAlign: 'center',
      padding: 'var(--spacing-xl)',
      color: 'var(--color-text-secondary)'
    }
  }, [
    props.icon ? createElement('div', { style: { fontSize: '48px', marginBottom: '16px' } }, [props.icon]) : null,
    createElement('p', {}, [props.message || 'No data available']),
    props.action ? createElement('button', {
      onClick: props.action.onClick,
      className: 'dnr-button dnr-button-primary',
      style: { marginTop: '16px' }
    }, [props.action.label]) : null
  ].filter(Boolean));
});

// Modal/Dialog
registerComponent('Modal', (props, children) => {
  if (!props.open) return null;

  const overlay = createElement('div', {
    className: 'dnr-modal-overlay',
    onClick: (e) => {
      if (e.target === e.currentTarget && props.onClose) props.onClose();
    },
    style: {
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }
  }, [
    createElement('div', {
      className: 'dnr-modal',
      style: {
        background: 'var(--color-background)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--spacing-lg)',
        maxWidth: props.maxWidth || '500px',
        width: '90%',
        maxHeight: '90vh',
        overflow: 'auto'
      }
    }, [
      createElement('div', {
        className: 'dnr-modal-header',
        style: {
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--spacing-md)'
        }
      }, [
        createElement('h2', { style: { margin: 0 } }, [props.title || '']),
        props.onClose ? createElement('button', {
          onClick: props.onClose,
          style: {
            background: 'none',
            border: 'none',
            fontSize: '24px',
            cursor: 'pointer',
            color: 'var(--color-text-secondary)'
          }
        }, ['×']) : null
      ].filter(Boolean)),
      createElement('div', { className: 'dnr-modal-body' }, children)
    ])
  ]);

  return overlay;
});

// =============================================================================
// Inject Spinner Animation
// =============================================================================

export function injectSpinnerStyles() {
  const spinnerStyle = document.createElement('style');
  spinnerStyle.textContent = `
    @keyframes dnr-spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
  `;
  if (typeof document !== 'undefined') {
    document.head.appendChild(spinnerStyle);
  }
}

// Auto-inject styles on import (browser only)
if (typeof document !== 'undefined') {
  injectSpinnerStyles();
}

export { componentRegistry };
