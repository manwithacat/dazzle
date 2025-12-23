/**
 * DNR-UI Components - Built-in UI primitives
 * Part of the Dazzle Native Runtime
 *
 * Uses DaisyUI (via CDN) + Tailwind for styling.
 * See: https://daisyui.com/components/
 *
 * All components support semantic attributes via the `dazzle` prop:
 * - dazzle.entity: Entity name context
 * - dazzle.field: Field identifier (Entity.field)
 * - dazzle.action: Action identifier (Entity.action)
 * - dazzle.view: View identifier
 * - etc. (see SEMANTIC_DOM_CONTRACT.md)
 *
 * Accessibility:
 * - Modal: Focus trap, Escape to close, ARIA attributes
 * - Toast: aria-live regions for screen readers
 * - Form elements: Proper labels and ARIA attributes
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
// Uses DaisyUI: btn, btn-primary, btn-secondary, btn-error, btn-ghost, btn-sm, btn-lg
registerComponent('Button', (props, children) => {
  const variant = props.variant || 'secondary';
  const size = props.size || 'default';

  // Map variants to DaisyUI classes
  const variantMap = {
    'primary': 'btn-primary',
    'secondary': 'btn-secondary',
    'danger': 'btn-error',
    'destructive': 'btn-error',
    'ghost': 'btn-ghost',
    'link': 'btn-link',
    'outline': 'btn-outline',
  };

  const sizeMap = {
    'xs': 'btn-xs',
    'sm': 'btn-sm',
    'lg': 'btn-lg',
    'xl': 'btn-xl',
  };

  const classNames = ['btn'];
  if (variantMap[variant]) classNames.push(variantMap[variant]);
  if (sizeMap[size]) classNames.push(sizeMap[size]);

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
// Uses DaisyUI: input, input-error, textarea
// Supports type-aware rendering: text, date, datetime, number, etc.
registerComponent('Input', (props) => {
  // DaisyUI input classes
  const classNames = ['input', 'input-bordered', 'w-full'];
  if (props.error) classNames.push('input-error');

  // Map field types to HTML input types
  const fieldType = props.fieldType || props.type || 'text';
  const inputTypeMap = {
    'str': 'text',
    'text': 'text',
    'int': 'number',
    'float': 'number',
    'decimal': 'number',
    'bool': 'checkbox',
    'date': 'date',
    'datetime': 'datetime-local',
    'time': 'time',
    'email': 'email',
    'url': 'url',
    'tel': 'tel',
    'password': 'password',
  };
  const htmlType = inputTypeMap[fieldType] || fieldType;

  // For textarea (text fields), use textarea element with DaisyUI classes
  if (fieldType === 'text' && props.multiline) {
    const el = createElement('textarea', {
      className: 'textarea textarea-bordered w-full' + (props.error ? ' textarea-error' : ''),
      value: props.value,
      placeholder: props.placeholder,
      disabled: props.disabled,
      required: props.required,
      rows: props.rows || 4,
      onInput: (e) => props.onChange && props.onChange(e.target.value)
    });

    return withDazzleAttrs(el, {
      field: props.dazzle?.field || props.field,
      fieldType: 'text',
      required: props.required,
      entity: props.dazzle?.entity,
      ...props.dazzle
    });
  }

  // Standard input element
  const inputProps = {
    className: classNames.join(' '),
    type: htmlType,
    value: props.value,
    placeholder: props.placeholder,
    disabled: props.disabled,
    required: props.required,
    onInput: (e) => props.onChange && props.onChange(
      htmlType === 'checkbox' ? e.target.checked : e.target.value
    )
  };

  // Add number-specific attributes
  if (htmlType === 'number') {
    if (props.min !== undefined) inputProps.min = props.min;
    if (props.max !== undefined) inputProps.max = props.max;
    if (props.step !== undefined) inputProps.step = props.step;
    // Default step for decimals
    if (fieldType === 'decimal' || fieldType === 'float') {
      inputProps.step = props.step || 'any';
    }
  }

  const el = createElement('input', inputProps);

  // Add semantic attributes for fields
  return withDazzleAttrs(el, {
    field: props.dazzle?.field || props.field,
    fieldType: fieldType,
    required: props.required,
    entity: props.dazzle?.entity,
    ...props.dazzle
  });
});

// Select component - dropdown for enum fields
// Uses DaisyUI: select, select-bordered, select-error
registerComponent('Select', (props) => {
  const classNames = ['select', 'select-bordered', 'w-full'];
  if (props.error) classNames.push('select-error');

  const options = props.options || [];

  // Build option elements
  const optionElements = [];

  // Add placeholder option if specified
  if (props.placeholder) {
    optionElements.push(
      createElement('option', { value: '', disabled: true, selected: !props.value }, [props.placeholder])
    );
  }

  // Add options
  options.forEach(opt => {
    const optValue = typeof opt === 'object' ? opt.value : opt;
    const optLabel = typeof opt === 'object' ? (opt.label || opt.value) : opt;
    // Format label: capitalize and replace underscores with spaces
    const displayLabel = optLabel.charAt(0).toUpperCase() + optLabel.slice(1).replace(/_/g, ' ');

    optionElements.push(
      createElement('option', {
        value: optValue,
        selected: props.value === optValue
      }, [displayLabel])
    );
  });

  const el = createElement('select', {
    className: classNames.join(' '),
    disabled: props.disabled,
    required: props.required,
    onChange: (e) => props.onChange && props.onChange(e.target.value)
  }, optionElements);

  // Add semantic attributes for fields
  return withDazzleAttrs(el, {
    field: props.dazzle?.field || props.field,
    fieldType: 'enum',
    required: props.required,
    entity: props.dazzle?.entity,
    ...props.dazzle
  });
});

// Checkbox component - for boolean fields
// Uses DaisyUI: checkbox, label with cursor-pointer
registerComponent('Checkbox', (props, children) => {
  const el = createElement('label', { className: 'label cursor-pointer justify-start gap-3' }, [
    createElement('input', {
      type: 'checkbox',
      className: 'checkbox',
      checked: props.checked || props.value,
      disabled: props.disabled,
      onChange: (e) => props.onChange && props.onChange(e.target.checked)
    }),
    createElement('span', { className: 'label-text' }, children.length ? children : [props.label || ''])
  ]);

  return withDazzleAttrs(el, {
    field: props.dazzle?.field || props.field,
    fieldType: 'bool',
    entity: props.dazzle?.entity,
    ...props.dazzle
  });
});

// Label component
// Uses DaisyUI: label, label-text
registerComponent('Label', (props, children) => {
  const labelContent = createElement('span', { className: 'label-text' }, children);

  // Add required indicator
  if (props.required) {
    const indicator = createElement('span', { className: 'text-error ml-1' }, ['*']);
    labelContent.appendChild(indicator);
  }

  const el = createElement('label', {
    className: 'label',
    htmlFor: props.for
  }, [labelContent]);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// DataTable component - represents an entity list
// Uses DaisyUI: table, table-zebra, btn btn-sm
registerComponent('DataTable', (props) => {
  const { columns, data, onRowClick, entity, showActions = true } = props;
  const entityName = props.dazzle?.entity || entity;
  const striped = props.striped !== false; // Default to true

  // DaisyUI table classes
  const tableClasses = ['table', 'w-full'];
  if (striped) tableClasses.push('table-zebra');

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
      createElement('th', { className: 'text-right' }, ['Actions'])
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
      // Edit button - DaisyUI
      const editBtn = withDazzleAttrs(
        createElement('button', {
          className: 'btn btn-secondary btn-sm',
          onClick: (e) => {
            e.stopPropagation();
            window.dispatchEvent(new CustomEvent('dnr-navigate', {
              detail: { url: `/${entityName.toLowerCase()}/${rowId}/edit` }
            }));
          }
        }, ['Edit']),
        { action: `${entityName}.edit`, actionRole: 'secondary', entityId: rowId }
      );

      // Delete button - DaisyUI with custom confirmation dialog
      const deleteBtn = withDazzleAttrs(
        createElement('button', {
          className: 'btn btn-error btn-sm',
          onClick: (e) => {
            e.stopPropagation();
            // Show delete confirmation dialog
            window.dispatchEvent(new CustomEvent('dnr-confirm-delete', {
              detail: { entity: entityName, id: rowId }
            }));
          }
        }, ['Delete']),
        { action: `${entityName}.delete`, actionRole: 'destructive', entityId: rowId }
      );

      cells.push(
        createElement('td', { className: 'text-right' }, [
          createElement('div', { className: 'flex gap-2 justify-end' }, [editBtn, deleteBtn])
        ])
      );
    }

    // Default row click navigates to detail view if entity has one
    const handleRowClick = onRowClick || (entityName ? () => {
      window.dispatchEvent(new CustomEvent('dnr-navigate', {
        detail: { url: `/${entityName.toLowerCase()}/${rowId}` }
      }));
    } : null);

    const tr = createElement('tr', {
      className: handleRowClick ? 'hover cursor-pointer' : '',
      onClick: handleRowClick
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
// Uses DaisyUI: card structure with Tailwind flex utilities
// Automatically handles form submission to API and navigation
registerComponent('Form', (props, children) => {
  const entityName = props.dazzle?.entity || props.entity;
  const formMode = props.dazzle?.formMode || props.mode || 'create';
  const entityId = props.dazzle?.entityId || props.entityId;

  // Build API endpoint (DNR routes are at /entitys, not /api/entitys)
  const apiEndpoint = entityName ? `/${entityName.toLowerCase()}s` : null;

  const el = createElement('form', {
    className: 'flex flex-col gap-4 max-w-lg',
    onSubmit: async (e) => {
      e.preventDefault();

      // If custom onSubmit provided, use it
      if (props.onSubmit) {
        props.onSubmit(e);
        return;
      }

      // Otherwise, handle form submission automatically
      if (!apiEndpoint || !entityName) {
        console.warn('Form: No entity specified, cannot submit');
        return;
      }

      // Collect form data from all data-dazzle-field elements
      const formData = {};
      const form = e.target;
      const fieldElements = form.querySelectorAll('[data-dazzle-field]');

      fieldElements.forEach((field) => {
        const fieldAttr = field.getAttribute('data-dazzle-field');
        // Field format is "Entity.fieldName" - extract fieldName
        const fieldName = fieldAttr.includes('.') ? fieldAttr.split('.')[1] : fieldAttr;

        let value;
        if (field.tagName === 'INPUT') {
          if (field.type === 'checkbox') {
            value = field.checked;
          } else {
            value = field.value;
          }
        } else if (field.tagName === 'SELECT') {
          value = field.value;
        } else if (field.tagName === 'TEXTAREA') {
          value = field.value;
        }

        // Convert empty strings to null for API compatibility
        // (empty optional fields should be null, not "")
        formData[fieldName] = value === '' ? null : value;
      });

      try {
        const isCreate = formMode === 'create';
        const url = isCreate ? apiEndpoint : `${apiEndpoint}/${entityId}`;
        const method = isCreate ? 'POST' : 'PUT';

        const response = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData),
        });

        if (response.ok) {
          // Navigate to list view
          const listUrl = `/${entityName.toLowerCase()}`;
          window.dispatchEvent(new CustomEvent('dnr-navigate', {
            detail: { url: listUrl }
          }));
        } else {
          const errorData = await response.json().catch(() => ({}));
          alert(`Failed to ${isCreate ? 'create' : 'update'}: ${errorData.detail || response.statusText}`);
        }
      } catch (err) {
        console.error('Form submission error:', err);
        alert(`Failed to submit form: ${err.message}`);
      }
    }
  }, [
    props.title ? createElement('h2', { className: 'text-xl font-semibold mb-2' }, [props.title]) : null,
    ...children
  ].filter(Boolean));

  // Add semantic attributes for forms
  return withDazzleAttrs(el, {
    form: entityName,
    formMode: formMode,
    entity: entityName,
    entityId: entityId,
    ...props.dazzle
  });
});

// FormGroup component - wraps label + input
// Uses DaisyUI: fieldset structure
registerComponent('FormGroup', (props, children) => {
  const el = createElement('fieldset', { className: 'fieldset' }, children);
  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// FormActions component - container for form buttons
registerComponent('FormActions', (props, children) => {
  const el = createElement('div', { className: 'flex gap-3 pt-4 border-t border-base-300 mt-2' }, children);
  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Stack (flexbox) component - uses Tailwind utilities
registerComponent('Stack', (props, children) => {
  const classNames = ['flex'];

  // Direction
  if (props.direction === 'row') {
    classNames.push('flex-row');
  } else {
    classNames.push('flex-col');
  }

  // Wrap
  if (props.wrap) classNames.push('flex-wrap');

  // Alignment
  if (props.align === 'center') classNames.push('items-center');
  else if (props.align === 'stretch') classNames.push('items-stretch');

  // Justify
  if (props.justify === 'between') classNames.push('justify-between');
  else if (props.justify === 'center') classNames.push('justify-center');
  else if (props.justify === 'end') classNames.push('justify-end');

  // Gap
  const gapMap = { 'xs': 'gap-1', 'sm': 'gap-2', 'md': 'gap-4', 'lg': 'gap-6', 'xl': 'gap-8' };
  classNames.push(gapMap[props.gap] || 'gap-4');

  const el = createElement('div', { className: classNames.join(' ') }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Grid component - uses Tailwind grid utilities
registerComponent('Grid', (props, children) => {
  const cols = props.cols || 1;
  const colsMap = {
    1: 'grid-cols-1',
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
  };

  const classNames = ['grid', 'gap-4'];
  classNames.push(colsMap[cols] || 'grid-cols-1');

  const el = createElement('div', { className: classNames.join(' ') }, children);

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Track entities delete handlers: stores { apiEndpoint, fetchData } per entity
// This prevents duplicate handlers and allows updating the fetchData reference
const entityDeleteRegistry = new Map();

// FilterableTable pattern component with auto-fetch
// Uses DaisyUI: card, btn, input, table patterns
registerComponent('FilterableTable', (props) => {
  const entityName = props.dazzle?.entity || props.entity;
  const viewName = props.dazzle?.view || props.view;
  const title = props.title || (entityName ? `${entityName} List` : 'Items');
  const columns = props.columns || [];
  const apiEndpoint = props.apiEndpoint;

  // Create container element - using DaisyUI card
  const container = createElement('div', { className: 'card bg-base-100 shadow-sm' });

  // Create "Create" button with semantic attributes - DaisyUI btn
  const createBtn = withDazzleAttrs(
    createElement('button', {
      className: 'btn btn-primary',
      onClick: () => {
        window.dispatchEvent(new CustomEvent('dnr-navigate', {
          detail: { url: `/${entityName ? entityName.toLowerCase() : 'item'}/create` }
        }));
      }
    }, [`Create ${entityName || 'Item'}`]),
    { action: `${entityName}.create`, actionRole: 'primary' }
  );

  // Create header with title and actions - DaisyUI card-body styling
  const header = createElement('div', {
    className: 'flex justify-between items-center p-4 border-b border-base-300'
  }, [
    createElement('h2', { className: 'text-xl font-semibold' }, [title]),
    createElement('div', {}, [createBtn])
  ]);

  // Create filter input - DaisyUI input
  const filterSection = createElement('div', { className: 'p-4 border-b border-base-300' }, [
    props.filterPlaceholder ?
      createElement('input', {
        type: 'text',
        className: 'input input-bordered w-full max-w-xs',
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
              detail: { url: `/${entityName ? entityName.toLowerCase() : 'item'}/create` }
            }));
          }
        }
      });
      container.appendChild(emptyEl);
    } else {
      // Table body wrapper - using DaisyUI overflow pattern
      const bodyWrapper = createElement('div', { className: 'overflow-x-auto' });
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

      // v0.14.2: Check content-type before parsing JSON
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) {
          throw new Error(
            `API returned HTML instead of JSON for ${apiEndpoint}. ` +
            'Check that the backend is running and proxy is configured.'
          );
        }
        throw new Error(`Unexpected content type: ${contentType || 'unknown'}`);
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

  // Register delete handler (only once per entity, but update fetchData reference)
  if (entityName) {
    // Check if handler already registered
    const existingRegistry = entityDeleteRegistry.get(entityName);
    const handlerRegistered = existingRegistry?.handlerRegistered || false;

    // Update registry with current apiEndpoint and fetchData (preserving handlerRegistered)
    entityDeleteRegistry.set(entityName, { apiEndpoint, fetchData, handlerRegistered });

    // Only add the event listener once per entity
    if (!handlerRegistered) {
      entityDeleteRegistry.get(entityName).handlerRegistered = true;

      const handleDelete = async (event) => {
        if (event.detail.entity === entityName) {
          const id = event.detail.id;
          const registry = entityDeleteRegistry.get(entityName);
          if (!registry) return;

          try {
            const response = await fetch(`${registry.apiEndpoint}/${id}`, { method: 'DELETE' });
            if (response.ok) {
              registry.fetchData();
            } else {
              alert(`Failed to delete: ${response.statusText}`);
            }
          } catch (err) {
            alert(`Failed to delete: ${err.message}`);
          }
        }
      };
      window.addEventListener('dnr-delete', handleDelete);
    }
  }

  return withDazzleAttrs(container, {
    view: viewName,
    entity: entityName,
    ...props.dazzle
  });
});

// Loading indicator
// Uses DaisyUI: loading spinner
registerComponent('Loading', (props) => {
  const el = createElement('div', { className: 'flex items-center justify-center gap-3 p-8' }, [
    createElement('span', { className: 'loading loading-spinner loading-md' }),
    props.text ? createElement('span', { className: 'text-base-content/70' }, [props.text]) : null
  ].filter(Boolean));

  return withDazzleAttrs(el, {
    loading: props.dazzle?.loading || props.context || 'true',
    ...props.dazzle
  });
});

// Skeleton loader
// Uses DaisyUI: skeleton
registerComponent('Skeleton', (props) => {
  const width = props.width || '100%';
  const height = props.height || '1rem';

  const el = createElement('div', {
    className: 'skeleton',
    style: { width, height }
  });

  return el;
});

// Error display
// Uses DaisyUI: alert alert-error
registerComponent('Error', (props) => {
  const el = createElement('div', {
    className: 'alert alert-error'
  }, [
    createElement('div', {}, [
      createElement('strong', {}, [props.title || 'Error']),
      props.message ? createElement('p', { className: 'mt-1 text-sm' }, [props.message]) : null
    ]),
    props.onRetry ? createElement('button', {
      className: 'btn btn-sm',
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
// Uses DaisyUI: flex layout with btn
registerComponent('Empty', (props) => {
  const entityName = props.dazzle?.entity || props.entity;

  const actionButton = props.action ? withDazzleAttrs(
    createElement('button', {
      onClick: props.action.onClick,
      className: 'btn btn-primary'
    }, [props.action.label]),
    { action: props.action.name || `${entityName}.create`, actionRole: 'primary' }
  ) : null;

  const el = createElement('div', { className: 'flex flex-col items-center justify-center py-12 px-4 text-center' }, [
    props.icon ? createElement('div', { className: 'text-4xl mb-4 opacity-50' }, [props.icon]) : null,
    createElement('p', { className: 'text-lg font-medium text-base-content' }, [props.title || 'No data']),
    createElement('p', { className: 'text-base-content/60 mt-1' }, [props.message || 'No data available']),
    actionButton ? createElement('div', { className: 'mt-4' }, [actionButton]) : null
  ].filter(Boolean));

  if (props.dazzle) {
    return withDazzleAttrs(el, props.dazzle);
  }
  return el;
});

// Badge component
// Uses DaisyUI: badge, badge-primary, etc.
registerComponent('Badge', (props, children) => {
  const variant = props.variant || 'default';
  const variantMap = {
    'default': 'badge-ghost',
    'primary': 'badge-primary',
    'secondary': 'badge-secondary',
    'success': 'badge-success',
    'warning': 'badge-warning',
    'error': 'badge-error',
    'info': 'badge-info',
  };

  const classNames = ['badge'];
  if (variantMap[variant]) classNames.push(variantMap[variant]);

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

// Modal/Dialog - Accessible modal with focus trap and ARIA attributes
// Uses DaisyUI modal pattern with proper a11y
registerComponent('Modal', (props, children) => {
  if (!props.open) return null;

  const dialogName = props.dazzle?.dialog || props.name || 'modal';
  const titleId = `modal-title-${dialogName}`;
  const descId = `modal-desc-${dialogName}`;

  // Title element with proper ID for aria-labelledby
  const titleEl = createElement('h2', {
    className: 'text-lg font-bold',
    id: titleId
  }, [props.title || '']);
  withDazzleAttrs(titleEl, { dialogTitle: true });

  // Close button with proper accessibility
  const closeBtn = props.onClose ? withDazzleAttrs(
    createElement('button', {
      className: 'btn btn-sm btn-circle btn-ghost absolute right-2 top-2',
      onClick: props.onClose,
      'aria-label': 'Close modal'
    }, ['✕']),
    { action: 'cancel', actionRole: 'cancel' }
  ) : null;

  // Content element
  const contentEl = createElement('div', {
    className: 'py-4',
    id: descId
  }, children);
  withDazzleAttrs(contentEl, { dialogContent: true });

  // Footer with actions
  const footerEl = props.footer ? createElement('div', {
    className: 'modal-action'
  }, [props.footer]) : null;
  if (footerEl) {
    withDazzleAttrs(footerEl, { dialogActions: true });
  }

  // Dialog element with proper ARIA attributes
  const dialog = createElement('div', {
    className: 'modal-box relative',
    role: 'dialog',
    'aria-modal': 'true',
    'aria-labelledby': titleId,
    'aria-describedby': descId
  }, [
    closeBtn,
    titleEl,
    contentEl,
    footerEl
  ].filter(Boolean));

  // Overlay/backdrop - DaisyUI modal pattern
  const overlay = createElement('div', {
    className: 'modal modal-open',
    onClick: (e) => {
      // Close on backdrop click (outside dialog box)
      if (e.target === e.currentTarget && props.onClose) {
        props.onClose();
      }
    }
  }, [dialog]);

  // Focus trap and keyboard handling
  // Store reference for cleanup
  const previousActiveElement = document.activeElement;

  // Set up focus trap and keyboard handling after render
  setTimeout(() => {
    // Focus the dialog
    dialog.setAttribute('tabindex', '-1');
    dialog.focus();

    // Get all focusable elements within dialog
    const getFocusableElements = () => {
      return dialog.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
    };

    // Keyboard handler for Escape and Tab trap
    const handleKeyDown = (e) => {
      // Close on Escape
      if (e.key === 'Escape' && props.onClose) {
        e.preventDefault();
        props.onClose();
        return;
      }

      // Focus trap on Tab
      if (e.key === 'Tab') {
        const focusable = getFocusableElements();
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    overlay.addEventListener('keydown', handleKeyDown);

    // Focus first focusable element or the dialog itself
    const focusable = getFocusableElements();
    if (focusable.length > 0) {
      focusable[0].focus();
    }

    // Store cleanup function
    overlay._modalCleanup = () => {
      overlay.removeEventListener('keydown', handleKeyDown);
      // Restore focus to previous element
      if (previousActiveElement && previousActiveElement.focus) {
        previousActiveElement.focus();
      }
    };
  }, 0);

  // Add cleanup on removal (via MutationObserver or manual call)
  const originalRemove = overlay.remove?.bind(overlay);
  overlay.remove = function() {
    if (overlay._modalCleanup) {
      overlay._modalCleanup();
    }
    if (originalRemove) {
      originalRemove();
    }
  };

  return withDazzleAttrs(overlay, {
    dialog: dialogName,
    dialogOpen: 'true',
    ...props.dazzle
  });
});

// Toast notification container - DaisyUI toast pattern
registerComponent('ToastContainer', (props, children) => {
  const position = props.position || 'top-end';
  const positionMap = {
    'top-start': 'toast toast-top toast-start',
    'top-center': 'toast toast-top toast-center',
    'top-end': 'toast toast-top toast-end',
    'bottom-start': 'toast toast-bottom toast-start',
    'bottom-center': 'toast toast-bottom toast-center',
    'bottom-end': 'toast toast-bottom toast-end',
  };

  const el = createElement('div', {
    className: positionMap[position] || 'toast toast-top toast-end',
    role: 'region',
    'aria-label': 'Notifications',
    'aria-live': 'polite'
  }, children);
  return el;
});

// Toast notification - DaisyUI alert with a11y
registerComponent('Toast', (props, children) => {
  const variant = props.variant || 'info';
  const variantMap = {
    'info': 'alert-info',
    'success': 'alert-success',
    'warning': 'alert-warning',
    'error': 'alert-error',
  };

  const classNames = ['alert', 'shadow-lg'];
  if (variantMap[variant]) classNames.push(variantMap[variant]);

  const el = createElement('div', {
    className: classNames.join(' '),
    role: 'alert',
    'aria-live': variant === 'error' ? 'assertive' : 'polite'
  }, [
    createElement('span', {}, children),
    props.onClose ? createElement('button', {
      className: 'btn btn-sm btn-ghost',
      onClick: props.onClose,
      'aria-label': 'Dismiss notification'
    }, ['✕']) : null
  ].filter(Boolean));

  return el;
});

// =============================================================================
// Static Page Component
// =============================================================================

// StaticPage - renders markdown or HTML content for legal pages, about, etc.
// Uses DaisyUI prose class for nice typography
registerComponent('StaticPage', (props) => {
  const { title, content, loading, error } = props;

  // Error state
  if (error) {
    return createElement('div', { className: 'p-8' }, [
      createElement('div', { className: 'alert alert-error' }, [
        createElement('span', {}, [error])
      ])
    ]);
  }

  // Loading state
  if (loading) {
    return createElement('div', { className: 'flex justify-center items-center p-8' }, [
      createElement('span', { className: 'loading loading-spinner loading-lg' })
    ]);
  }

  // Content container with nice typography
  const el = createElement('article', {
    className: 'max-w-4xl mx-auto py-8 px-4'
  }, [
    title ? createElement('h1', {
      className: 'text-3xl font-bold mb-6'
    }, [title]) : null,
    createElement('div', {
      className: 'prose prose-lg max-w-none'
    })
  ].filter(Boolean));

  // Set HTML content (content is already HTML from backend)
  const contentDiv = el.querySelector('.prose');
  if (contentDiv && content) {
    contentDiv.innerHTML = content;
  }

  return el;
});

// =============================================================================
// Task Inbox Component (v0.24.0 - Process Human Tasks)
// =============================================================================

/**
 * Task Inbox - displays pending human tasks from workflow processes.
 * Uses DaisyUI card and alert components.
 */
registerComponent('TaskInbox', (props) => {
  const container = createElement('div', { className: 'task-inbox p-6' });

  // State
  let tasks = [];
  let loading = true;
  let error = null;
  let filter = props.filter || 'pending';

  // Add styles
  if (!document.getElementById('task-inbox-styles')) {
    const styles = document.createElement('style');
    styles.id = 'task-inbox-styles';
    styles.textContent = `
      .task-inbox { max-width: 900px; margin: 0 auto; }
      .task-inbox-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 0.75rem; }
      .task-inbox-actions { display: flex; align-items: center; gap: 0.5rem; }
      .task-inbox-loading { display: flex; flex-direction: column; align-items: center; padding: 3rem; }
      .task-inbox-empty { text-align: center; padding: 3rem; background: oklch(var(--b1)); border-radius: 0.75rem; border: 1px dashed oklch(var(--bc)/0.2); }
      .task-inbox-list { display: flex; flex-direction: column; gap: 0.75rem; }
      .task-item { border-left: 4px solid transparent; cursor: pointer; transition: transform 0.15s; }
      .task-item:hover { transform: translateX(4px); }
      .task-item[data-urgency="critical"] { border-left-color: oklch(var(--er)); }
      .task-item[data-urgency="high"] { border-left-color: oklch(var(--wa)); }
      .task-item[data-urgency="medium"] { border-left-color: oklch(var(--in)); }
      .task-item[data-urgency="low"] { border-left-color: oklch(var(--su)); }
    `;
    document.head.appendChild(styles);
  }

  // Render function
  const render = () => {
    let contentHtml;

    if (loading) {
      contentHtml = `
        <div class="task-inbox-loading">
          <span class="loading loading-spinner loading-lg"></span>
          <p class="mt-4 opacity-60">Loading tasks...</p>
        </div>
      `;
    } else if (error) {
      contentHtml = `
        <div class="alert alert-error">
          <span>${escapeHtml(error)}</span>
          <button class="btn btn-sm" data-action="retry">Retry</button>
        </div>
      `;
    } else if (tasks.length === 0) {
      contentHtml = `
        <div class="task-inbox-empty">
          <div class="text-6xl mb-4">✓</div>
          <h2 class="text-xl font-semibold">No pending tasks</h2>
          <p class="opacity-60 mt-2">You're all caught up!</p>
        </div>
      `;
    } else {
      const taskItems = tasks.map(task => {
        const urgency = getUrgency(task);
        const urgencyIcon = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' }[urgency];
        const timeInfo = task.is_overdue ? 'Overdue' : getTimeLeft(task.due_at);
        const surfaceUrl = `/surfaces/${task.surface_name}/${task.entity_id}?task_id=${task.task_id}&return_url=/workspaces/tasks`;

        return `
          <div class="task-item card bg-base-100 shadow-sm hover:shadow-md"
               data-task-id="${task.task_id}"
               data-surface-url="${surfaceUrl}"
               data-urgency="${urgency}">
            <div class="card-body p-4">
              <div class="flex items-start gap-3">
                <div class="text-2xl" title="${urgency}">${urgencyIcon}</div>
                <div class="flex-1 min-w-0">
                  <h3 class="font-semibold text-lg truncate">${escapeHtml(task.step_name)}</h3>
                  <p class="text-sm opacity-60 truncate">
                    ${task.process_name ? escapeHtml(task.process_name) + ' • ' : ''}${escapeHtml(task.entity_name)}
                  </p>
                </div>
                <div class="text-right">
                  <div class="${task.is_overdue ? 'text-error font-semibold' : 'opacity-60'}">${timeInfo}</div>
                  ${task.status === 'escalated' ? '<span class="badge badge-warning badge-sm">Escalated</span>' : ''}
                </div>
              </div>
            </div>
          </div>
        `;
      }).join('');

      contentHtml = `<div class="task-inbox-list">${taskItems}</div>`;
    }

    container.innerHTML = `
      <div class="task-inbox-header">
        <h1 class="text-2xl font-bold">My Tasks</h1>
        <div class="task-inbox-actions">
          <select class="select select-bordered select-sm" data-action="filter">
            <option value="pending" ${filter === 'pending' ? 'selected' : ''}>Pending</option>
            <option value="escalated" ${filter === 'escalated' ? 'selected' : ''}>Escalated</option>
            <option value="all" ${filter === 'all' ? 'selected' : ''}>All</option>
          </select>
          <button class="btn btn-sm btn-ghost" data-action="refresh" title="Refresh">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>
      ${contentHtml}
    `;

    // Attach event handlers
    container.querySelector('[data-action="filter"]')?.addEventListener('change', (e) => {
      filter = e.target.value;
      fetchTasks();
    });
    container.querySelector('[data-action="refresh"]')?.addEventListener('click', fetchTasks);
    container.querySelector('[data-action="retry"]')?.addEventListener('click', fetchTasks);

    // Task click handlers
    container.querySelectorAll('.task-item').forEach(item => {
      item.addEventListener('click', () => {
        const url = item.getAttribute('data-surface-url');
        if (url) {
          window.dispatchEvent(new CustomEvent('dnr-navigate', { detail: { url } }));
        }
      });
    });
  };

  // Fetch tasks from API
  const fetchTasks = async () => {
    loading = true;
    error = null;
    render();

    try {
      const params = new URLSearchParams();
      if (filter && filter !== 'all') {
        params.set('status', filter);
      }

      const response = await fetch(`/api/tasks?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Failed to load tasks: ${response.status}`);
      }

      const data = await response.json();
      tasks = data.tasks || [];
      loading = false;
      render();
    } catch (e) {
      loading = false;
      error = e.message;
      render();
    }
  };

  // Helper functions
  const getUrgency = (task) => {
    if (task.is_overdue) return 'critical';
    const dueAt = new Date(task.due_at);
    const now = new Date();
    const hoursLeft = (dueAt - now) / (1000 * 60 * 60);
    if (hoursLeft < 2) return 'high';
    if (hoursLeft < 24) return 'medium';
    return 'low';
  };

  const getTimeLeft = (dueAt) => {
    const due = new Date(dueAt);
    const now = new Date();
    const diffMs = due - now;
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 60) return `${diffMins}m left`;
    if (diffHours < 24) return `${diffHours}h left`;
    return `${diffDays}d left`;
  };

  const escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  };

  // Initial render and fetch
  render();
  setTimeout(fetchTasks, 0);

  // Refresh every 30 seconds
  const refreshInterval = setInterval(fetchTasks, 30000);

  // Cleanup on removal
  const originalRemove = container.remove?.bind(container);
  container.remove = function() {
    clearInterval(refreshInterval);
    if (originalRemove) originalRemove();
  };

  return withDazzleAttrs(container, {
    view: 'task-inbox',
    ...props.dazzle
  });
});

// =============================================================================
// Global Delete Confirmation Dialog
// =============================================================================

// Create and manage a global delete confirmation dialog
// Uses DaisyUI modal with data-dazzle-* attributes for Playwright compatibility
let deleteDialogInitialized = false;
const initDeleteConfirmDialog = () => {
  // Prevent multiple initializations
  if (deleteDialogInitialized) return;
  deleteDialogInitialized = true;

  let dialogEl = null;
  let pendingDelete = null;

  const createDialog = () => {
    if (dialogEl) return dialogEl;

    // Create modal backdrop
    const backdrop = createElement('div', {
      className: 'modal modal-open',
      onClick: (e) => {
        if (e.target === backdrop) hideDialog();
      }
    });

    // Create modal box
    const modalBox = createElement('div', { className: 'modal-box' }, [
      createElement('h3', { className: 'font-bold text-lg' }, ['Confirm Delete']),
      createElement('p', { className: 'py-4', id: 'delete-dialog-message' }, ['Are you sure you want to delete this item?']),
      createElement('div', { className: 'modal-action' }, [
        withDazzleAttrs(
          createElement('button', {
            className: 'btn',
            onClick: hideDialog
          }, ['Cancel']),
          { action: 'cancel', actionRole: 'cancel' }
        ),
        withDazzleAttrs(
          createElement('button', {
            className: 'btn btn-error',
            onClick: confirmDelete
          }, ['Delete']),
          { action: 'confirm-delete', actionRole: 'destructive' }
        )
      ])
    ]);

    backdrop.appendChild(modalBox);
    withDazzleAttrs(backdrop, { dialog: 'delete-confirm' });

    dialogEl = backdrop;
    return dialogEl;
  };

  const showDialog = (entity, id) => {
    pendingDelete = { entity, id };
    const dialog = createDialog();
    const message = dialog.querySelector('#delete-dialog-message');
    if (message) {
      message.textContent = `Are you sure you want to delete this ${entity}?`;
    }
    document.body.appendChild(dialog);
  };

  const hideDialog = () => {
    if (dialogEl && dialogEl.parentNode) {
      dialogEl.parentNode.removeChild(dialogEl);
    }
    pendingDelete = null;
  };

  const confirmDelete = () => {
    if (pendingDelete) {
      window.dispatchEvent(new CustomEvent('dnr-delete', {
        detail: pendingDelete
      }));
    }
    hideDialog();
  };

  // Listen for delete confirmation requests
  window.addEventListener('dnr-confirm-delete', (event) => {
    const { entity, id } = event.detail;
    showDialog(entity, id);
  });
};

// Initialize the delete confirmation dialog when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDeleteConfirmDialog);
} else {
  initDeleteConfirmDialog();
}

// =============================================================================
// Export
// =============================================================================

export { componentRegistry };
