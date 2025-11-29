/**
 * DNR-UI Components - Built-in UI primitives
 * Part of the Dazzle Native Runtime
 *
 * Uses DDT (Dazzle Design Tokens) semantic classes for styling.
 * See: runtime/static/css/components.css
 *
 * All components support semantic attributes via the `dazzle` prop:
 * - dazzle.entity: Entity name context
 * - dazzle.field: Field identifier (Entity.field)
 * - dazzle.action: Action identifier (Entity.action)
 * - dazzle.view: View identifier
 * - etc. (see SEMANTIC_DOM_CONTRACT.md)
 */

import { createElement, withDazzleAttrs } from './dom.js';

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
// Built-in Primitives (using DDT semantic classes)
// =============================================================================

// Page component - represents a view/screen
registerComponent('Page', (props, children) => {
  const el = createElement('div', {
    className: 'dz-page'
  }, [
    props.title ? createElement('div', { className: 'dz-page__header' }, [
      createElement('h1', { className: 'dz-page__title' }, [props.title]),
      props.subtitle ? createElement('p', { className: 'dz-page__subtitle' }, [props.subtitle]) : null
    ].filter(Boolean)) : null,
    createElement('div', { className: 'dz-page__content' }, children)
  ].filter(Boolean));

  // Add semantic attributes
  return withDazzleAttrs(el, {
    view: props.dazzle?.view || props.view,
    entity: props.dazzle?.entity || props.entity,
    ...props.dazzle
  });
});

// Card component
registerComponent('Card', (props, children) => {
  const el = createElement('div', {
    className: 'dz-card'
  }, [
    props.title ? createElement('div', { className: 'dz-card__header' }, [
      createElement('h2', { className: 'dz-card__title' }, [props.title])
    ]) : null,
    createElement('div', { className: 'dz-card__body' }, children)
  ].filter(Boolean));

  // Add semantic attributes
  return withDazzleAttrs(el, {
    view: props.dazzle?.view,
    entity: props.dazzle?.entity,
    ...props.dazzle
  });
});

// Surface component - container for content regions
registerComponent('Surface', (props, children) => {
  const variant = props.variant || 'default';
  const classNames = ['dz-surface'];
  if (variant === 'elevated') classNames.push('dz-surface--elevated');
  if (variant === 'flush') classNames.push('dz-surface--flush');

  const el = createElement('div', {
    className: classNames.join(' ')
  }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Text component
registerComponent('Text', (props, children) => {
  const variant = props.variant || 'body';
  const tag = variant === 'heading' ? 'h2' :
              variant === 'subheading' ? 'h3' :
              variant === 'label' ? 'label' : 'p';

  const classNames = ['dz-text'];
  if (variant === 'label') classNames.push('dz-label');
  if (props.muted) classNames.push('dz-text-muted');

  const el = createElement(tag, { className: classNames.join(' ') }, children);

  // Add semantic attributes for labels
  if (props.dazzle || variant === 'label') {
    return withDazzleAttrs(el, {
      label: props.dazzle?.label || props.for,
      ...props.dazzle
    });
  }
  return el;
});

// Button component - represents an action
registerComponent('Button', (props, children) => {
  const variant = props.variant || 'secondary';
  const size = props.size || 'default';

  const classNames = ['dz-button'];
  classNames.push(`dz-button--${variant}`);
  if (size !== 'default') classNames.push(`dz-button--${size}`);

  const el = createElement('button', {
    className: classNames.join(' '),
    onClick: props.onClick,
    disabled: props.disabled,
    type: props.type || 'button'
  }, children.length ? children : [props.label]);

  // Add semantic attributes for actions
  const actionRole = variant === 'primary' ? 'primary' :
                     variant === 'danger' || variant === 'destructive' ? 'destructive' :
                     variant === 'secondary' ? 'secondary' : undefined;

  return withDazzleAttrs(el, {
    action: props.dazzle?.action || props.action,
    actionRole: props.dazzle?.actionRole || actionRole,
    loading: props.loading,
    ...props.dazzle
  });
});

// Input component - represents a field input
registerComponent('Input', (props) => {
  const classNames = ['dz-input'];
  if (props.error) classNames.push('dz-input--error');

  const el = createElement('input', {
    className: classNames.join(' '),
    type: props.type || 'text',
    value: props.value,
    placeholder: props.placeholder,
    disabled: props.disabled,
    required: props.required,
    onInput: (e) => props.onChange && props.onChange(e.target.value)
  });

  // Add semantic attributes for fields
  return withDazzleAttrs(el, {
    field: props.dazzle?.field || props.field,
    fieldType: props.dazzle?.fieldType || props.type || 'text',
    required: props.required,
    entity: props.dazzle?.entity,
    ...props.dazzle
  });
});

// Label component
registerComponent('Label', (props, children) => {
  const classNames = ['dz-label'];
  if (props.required) classNames.push('dz-label--required');

  const el = createElement('label', {
    className: classNames.join(' '),
    htmlFor: props.for
  }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// DataTable component - represents an entity list
registerComponent('DataTable', (props) => {
  const { columns, data, onRowClick, entity, showActions = true } = props;
  const entityName = props.dazzle?.entity || entity;
  const compact = props.compact || false;
  const striped = props.striped !== false; // Default to true

  const tableClasses = ['dz-table'];
  if (compact) tableClasses.push('dz-table--compact');
  if (striped) tableClasses.push('dz-table--striped');

  // Create header row with optional actions column
  const headerCells = (columns || []).map(col => {
    const th = createElement('th', {}, [col.label || col.key]);
    if (entityName) {
      withDazzleAttrs(th, { column: `${entityName}.${col.key}` });
    }
    return th;
  });

  // Add actions column header if showActions is true
  if (showActions && entityName) {
    headerCells.push(
      createElement('th', { className: 'dz-text-right' }, ['Actions'])
    );
  }

  const thead = createElement('thead', {}, [
    createElement('tr', {}, headerCells)
  ]);

  const tbody = createElement('tbody', {}, (data || []).map((row, _idx) => {
    const rowId = row.id || row.uuid || row._id;

    // Create data cells
    const cells = (columns || []).map(col => {
      const td = createElement('td', {}, [row[col.key]]);
      if (entityName) {
        withDazzleAttrs(td, { cell: `${entityName}.${col.key}` });
      }
      return td;
    });

    // Add actions cell if showActions is true
    if (showActions && entityName) {
      // Edit button
      const editBtn = withDazzleAttrs(
        createElement('button', {
          className: 'dz-button dz-button--secondary dz-button--sm',
          onClick: (e) => {
            e.stopPropagation();
            window.dispatchEvent(new CustomEvent('dnr-navigate', {
              detail: { url: `/${entityName.toLowerCase()}/${rowId}/edit` }
            }));
          }
        }, ['Edit']),
        { action: `${entityName}.edit`, actionRole: 'secondary', entityId: rowId }
      );

      // Delete button
      const deleteBtn = withDazzleAttrs(
        createElement('button', {
          className: 'dz-button dz-button--danger dz-button--sm',
          onClick: (e) => {
            e.stopPropagation();
            if (confirm(`Are you sure you want to delete this ${entityName}?`)) {
              window.dispatchEvent(new CustomEvent('dnr-delete', {
                detail: { entity: entityName, id: rowId }
              }));
            }
          }
        }, ['Delete']),
        { action: `${entityName}.delete`, actionRole: 'destructive', entityId: rowId }
      );

      cells.push(
        createElement('td', { className: 'dz-text-right' }, [
          createElement('div', { className: 'dz-flex dz-gap-2 dz-justify-end' }, [editBtn, deleteBtn])
        ])
      );
    }

    const tr = createElement('tr', {
      onClick: () => onRowClick && onRowClick(row),
      style: { cursor: onRowClick ? 'pointer' : 'default' }
    }, cells);

    // Add row semantic attributes
    if (entityName) {
      withDazzleAttrs(tr, {
        entity: entityName,
        row: entityName,
        entityId: rowId
      });
    }
    return tr;
  }));

  const table = createElement('table', {
    className: tableClasses.join(' ')
  }, [thead, tbody]);

  // Add table semantic attributes
  return withDazzleAttrs(table, {
    table: entityName
  });
});

// Form component - represents an entity form
registerComponent('Form', (props, children) => {
  const el = createElement('form', {
    className: 'dz-form',
    onSubmit: (e) => {
      e.preventDefault();
      props.onSubmit && props.onSubmit(e);
    }
  }, [
    props.title ? createElement('h2', { className: 'dz-card__title dz-mb-4' }, [props.title]) : null,
    ...children
  ].filter(Boolean));

  // Add semantic attributes for forms
  const entityName = props.dazzle?.entity || props.entity;
  return withDazzleAttrs(el, {
    form: entityName,
    formMode: props.dazzle?.formMode || props.mode || 'create',
    entity: entityName,
    entityId: props.dazzle?.entityId || props.entityId,
    ...props.dazzle
  });
});

// FormGroup component - wraps label + input
registerComponent('FormGroup', (props, children) => {
  const el = createElement('div', { className: 'dz-form__group' }, children);
  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// FormActions component - container for form buttons
registerComponent('FormActions', (props, children) => {
  const el = createElement('div', { className: 'dz-form__actions' }, children);
  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Stack (flexbox) component
registerComponent('Stack', (props, children) => {
  const classNames = ['dz-stack'];
  if (props.direction === 'row') classNames.push('dz-stack--row');
  if (props.wrap) classNames.push('dz-stack--wrap');
  if (props.align === 'center') classNames.push('dz-stack--center');
  if (props.align === 'stretch') classNames.push('dz-stack--stretch');
  if (props.justify === 'between') classNames.push('dz-stack--between');

  // Add gap utility class
  const gap = props.gap || 'md';
  classNames.push(`dz-gap-${gap === 'sm' ? '2' : gap === 'md' ? '4' : gap === 'lg' ? '6' : '4'}`);

  const el = createElement('div', { className: classNames.join(' ') }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Grid component
registerComponent('Grid', (props, children) => {
  const cols = props.cols || 1;
  const classNames = ['dz-grid'];
  if (cols > 1) classNames.push(`dz-grid--cols-${cols}`);

  const el = createElement('div', { className: classNames.join(' ') }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// FilterableTable pattern component with auto-fetch
registerComponent('FilterableTable', (props) => {
  const entityName = props.dazzle?.entity || props.entity;
  const viewName = props.dazzle?.view || props.view;
  const title = props.title || (entityName ? `${entityName} List` : 'Items');
  const columns = props.columns || [];
  const apiEndpoint = props.apiEndpoint;

  // Create container element
  const container = createElement('div', { className: 'dz-filterable-table' });

  // Create "Create" button with semantic attributes
  const createBtn = withDazzleAttrs(
    createElement('button', {
      className: 'dz-button dz-button--primary',
      onClick: () => {
        window.dispatchEvent(new CustomEvent('dnr-navigate', {
          detail: { url: `/${entityName ? entityName.toLowerCase() : 'item'}/new` }
        }));
      }
    }, [`Create ${entityName || 'Item'}`]),
    { action: `${entityName}.create`, actionRole: 'primary' }
  );

  // Create header with title and actions
  const header = createElement('div', {
    className: 'dz-filterable-table__header'
  }, [
    createElement('h2', { className: 'dz-filterable-table__title' }, [title]),
    createElement('div', { className: 'dz-filterable-table__controls' }, [createBtn])
  ]);

  // Create filter input
  const filterSection = createElement('div', { className: 'dz-filterable-table__controls dz-mb-4' }, [
    props.filterPlaceholder ?
      createElement('input', {
        type: 'text',
        className: 'dz-input dz-filterable-table__search',
        placeholder: props.filterPlaceholder
      }) : null
  ].filter(Boolean));

  // Function to render the table content
  const renderContent = (data, loading, error) => {
    container.innerHTML = '';
    container.appendChild(header);
    if (props.filterPlaceholder) {
      container.appendChild(filterSection);
    }

    if (loading) {
      const loadingEl = componentRegistry.get('Loading')({ text: 'Loading...' });
      container.appendChild(loadingEl);
    } else if (error) {
      const errorEl = componentRegistry.get('Error')({
        title: 'Failed to load data',
        message: error,
        onRetry: () => fetchData()
      });
      container.appendChild(errorEl);
    } else if (!data || data.length === 0) {
      const emptyEl = componentRegistry.get('Empty')({
        message: `No ${entityName || 'items'} found`,
        entity: entityName,
        action: {
          label: `Create ${entityName || 'Item'}`,
          onClick: () => {
            window.dispatchEvent(new CustomEvent('dnr-navigate', {
              detail: { url: `/${entityName ? entityName.toLowerCase() : 'item'}/new` }
            }));
          }
        }
      });
      container.appendChild(emptyEl);
    } else {
      const bodyWrapper = createElement('div', { className: 'dz-filterable-table__body' });
      const tableEl = componentRegistry.get('DataTable')({
        columns: columns,
        data: data,
        entity: entityName,
        dazzle: { entity: entityName }
      });
      bodyWrapper.appendChild(tableEl);
      container.appendChild(bodyWrapper);
    }
  };

  // Function to fetch data from API
  const fetchData = async () => {
    if (!apiEndpoint) {
      renderContent(props.data || [], false, null);
      return;
    }

    renderContent(null, true, null);

    try {
      const response = await fetch(apiEndpoint);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const responseData = await response.json();
      const data = Array.isArray(responseData) ? responseData : (responseData.items || []);
      renderContent(data, false, null);
    } catch (err) {
      console.error('FilterableTable fetch error:', err);
      renderContent(null, false, err.message);
    }
  };

  // Initial render
  renderContent(null, true, null);
  setTimeout(() => fetchData(), 0);

  // Listen for delete events
  const handleDelete = async (event) => {
    if (event.detail.entity === entityName) {
      const id = event.detail.id;
      try {
        const response = await fetch(`${apiEndpoint}/${id}`, { method: 'DELETE' });
        if (response.ok) {
          fetchData();
        } else {
          alert(`Failed to delete: ${response.statusText}`);
        }
      } catch (err) {
        alert(`Failed to delete: ${err.message}`);
      }
    }
  };
  window.addEventListener('dnr-delete', handleDelete);

  return withDazzleAttrs(container, {
    view: viewName,
    entity: entityName,
    ...props.dazzle
  });
});

// Loading indicator
registerComponent('Loading', (props) => {
  const el = createElement('div', { className: 'dz-loading' }, [
    createElement('div', { className: 'dz-spinner' }),
    props.text ? createElement('span', { className: 'dz-text-muted' }, [props.text]) : null
  ].filter(Boolean));

  return withDazzleAttrs(el, {
    loading: props.dazzle?.loading || props.context || 'true',
    ...props.dazzle
  });
});

// Skeleton loader
registerComponent('Skeleton', (props) => {
  const width = props.width || '100%';
  const height = props.height || '1rem';

  const el = createElement('div', {
    className: 'dz-skeleton',
    style: { width, height }
  });

  return el;
});

// Error display
registerComponent('Error', (props) => {
  const el = createElement('div', {
    className: 'dz-toast dz-toast--error dz-p-4'
  }, [
    createElement('div', { className: 'dz-toast__message' }, [
      createElement('strong', {}, [props.title || 'Error']),
      props.message ? createElement('p', { className: 'dz-mt-2 dz-m-0' }, [props.message]) : null
    ]),
    props.onRetry ? createElement('button', {
      className: 'dz-button dz-button--danger dz-button--sm dz-mt-2',
      onClick: props.onRetry
    }, ['Retry']) : null
  ].filter(Boolean));

  return withDazzleAttrs(el, {
    message: props.dazzle?.message || props.target || 'global',
    messageKind: 'error',
    ...props.dazzle
  });
});

// Empty state
registerComponent('Empty', (props) => {
  const entityName = props.dazzle?.entity || props.entity;

  const actionButton = props.action ? withDazzleAttrs(
    createElement('button', {
      onClick: props.action.onClick,
      className: 'dz-button dz-button--primary'
    }, [props.action.label]),
    { action: props.action.name || `${entityName}.create`, actionRole: 'primary' }
  ) : null;

  const el = createElement('div', { className: 'dz-empty' }, [
    props.icon ? createElement('div', { className: 'dz-empty__icon' }, [props.icon]) : null,
    createElement('p', { className: 'dz-empty__title' }, [props.title || 'No data']),
    createElement('p', { className: 'dz-empty__description' }, [props.message || 'No data available']),
    actionButton
  ].filter(Boolean));

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Badge component
registerComponent('Badge', (props, children) => {
  const variant = props.variant || 'default';
  const classNames = ['dz-badge', `dz-badge--${variant}`];

  const el = createElement('span', { className: classNames.join(' ') }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Navigation component
registerComponent('Nav', (props, children) => {
  const el = createElement('nav', { className: 'dz-nav' }, [
    props.brand ? createElement('a', {
      className: 'dz-nav__brand',
      href: props.brandHref || '/'
    }, [props.brand]) : null,
    createElement('div', { className: 'dz-nav__links' }, children)
  ].filter(Boolean));

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// NavLink component
registerComponent('NavLink', (props, children) => {
  const classNames = ['dz-nav__link'];
  if (props.active) classNames.push('dz-nav__link--active');

  const el = createElement('a', {
    className: classNames.join(' '),
    href: props.href || '#',
    onClick: props.onClick
  }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Modal/Dialog
registerComponent('Modal', (props, children) => {
  if (!props.open) return null;

  const dialogName = props.dazzle?.dialog || props.name || 'modal';

  const titleEl = createElement('h2', { className: 'dz-dialog__title' }, [props.title || '']);
  withDazzleAttrs(titleEl, { dialogTitle: true });

  const closeBtn = props.onClose ? withDazzleAttrs(
    createElement('button', {
      className: 'dz-button dz-button--ghost',
      onClick: props.onClose
    }, ['×']),
    { action: 'cancel', actionRole: 'cancel' }
  ) : null;

  const contentEl = createElement('div', { className: 'dz-dialog__body' }, children);
  withDazzleAttrs(contentEl, { dialogContent: true });

  const overlay = createElement('div', {
    className: 'dz-dialog-overlay',
    onClick: (e) => {
      if (e.target === e.currentTarget && props.onClose) props.onClose();
    }
  }, [
    createElement('div', { className: 'dz-dialog' }, [
      createElement('div', { className: 'dz-dialog__header' }, [titleEl, closeBtn].filter(Boolean)),
      contentEl,
      props.footer ? createElement('div', { className: 'dz-dialog__footer' }, [props.footer]) : null
    ].filter(Boolean))
  ]);

  return withDazzleAttrs(overlay, {
    dialog: dialogName,
    dialogOpen: 'true',
    ...props.dazzle
  });
});

// Toast notification container
registerComponent('ToastContainer', (props, children) => {
  const el = createElement('div', { className: 'dz-toast-container' }, children);
  return el;
});

// Toast notification
registerComponent('Toast', (props, children) => {
  const variant = props.variant || 'info';
  const classNames = ['dz-toast', `dz-toast--${variant}`];

  const el = createElement('div', { className: classNames.join(' ') }, [
    createElement('div', { className: 'dz-toast__message' }, children),
    props.onClose ? createElement('button', {
      className: 'dz-toast__close',
      onClick: props.onClose
    }, ['×']) : null
  ].filter(Boolean));

  return el;
});

// =============================================================================
// Export
// =============================================================================

export { componentRegistry };
