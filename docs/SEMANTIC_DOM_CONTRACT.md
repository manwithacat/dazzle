# Dazzle Semantic DOM Contract

**Version**: 1.0
**Status**: Active
**Created**: 2025-11-29

This document defines the semantic HTML attributes that all Dazzle-generated UIs must include. These attributes enable stack-agnostic E2E testing by providing stable, semantic selectors.

---

## Attribute Prefix

All semantic attributes use the `data-dazzle-` prefix.

---

## Core Attributes

### Views / Pages

Identify the current view or page context.

```html
<div data-dazzle-view="task_list">...</div>
<div data-dazzle-view="task_detail">...</div>
<div data-dazzle-view="task_create">...</div>
```

**Naming Convention**: `{entity}_{mode}` where mode is `list`, `detail`, `create`, `edit`

---

### Entity Context

Mark elements that represent or contain entity data.

```html
<!-- Entity container -->
<div data-dazzle-entity="Task">...</div>

<!-- Entity instance with ID -->
<div data-dazzle-entity="Task" data-dazzle-entity-id="550e8400-e29b-41d4-a716-446655440000">
  ...
</div>
```

---

### Fields

Mark input elements and their associated labels.

```html
<!-- Text input -->
<input
  data-dazzle-field="Task.title"
  data-dazzle-field-type="text"
  data-dazzle-required="true"
/>

<!-- Checkbox -->
<input
  data-dazzle-field="Task.completed"
  data-dazzle-field-type="checkbox"
/>

<!-- Select/Dropdown -->
<select data-dazzle-field="Task.priority" data-dazzle-field-type="select">
  <option value="low">Low</option>
  <option value="high">High</option>
</select>

<!-- Field label -->
<label data-dazzle-label="Task.title">Title</label>

<!-- Field container (groups label + input + error) -->
<div data-dazzle-field-group="Task.title">
  <label data-dazzle-label="Task.title">Title</label>
  <input data-dazzle-field="Task.title" />
  <span data-dazzle-message="Task.title" data-dazzle-message-kind="validation"></span>
</div>
```

**Field Types**:
- `text` - Text input
- `textarea` - Multi-line text
- `number` - Numeric input
- `checkbox` - Boolean checkbox
- `select` - Dropdown selection
- `date` - Date picker
- `datetime` - DateTime picker
- `email` - Email input
- `url` - URL input
- `password` - Password input
- `file` - File upload

---

### Actions

Mark interactive elements that trigger operations.

```html
<!-- Primary action -->
<button
  data-dazzle-action="Task.create"
  data-dazzle-action-role="primary"
>
  Create Task
</button>

<!-- Secondary action -->
<button
  data-dazzle-action="Task.save"
  data-dazzle-action-role="secondary"
>
  Save
</button>

<!-- Destructive action -->
<button
  data-dazzle-action="Task.delete"
  data-dazzle-action-role="destructive"
>
  Delete
</button>

<!-- Cancel/dismiss action -->
<button
  data-dazzle-action="cancel"
  data-dazzle-action-role="cancel"
>
  Cancel
</button>

<!-- Navigation action -->
<a
  data-dazzle-action="navigate"
  data-dazzle-nav-target="task_list"
>
  Back to List
</a>
```

**Action Roles**:
- `primary` - Main action on the page
- `secondary` - Supporting action
- `destructive` - Delete/remove operations
- `cancel` - Cancel/dismiss operations
- `submit` - Form submission

**Standard Actions**:
- `{Entity}.create` - Create new entity
- `{Entity}.save` - Save entity changes
- `{Entity}.delete` - Delete entity
- `{Entity}.edit` - Enter edit mode
- `{Entity}.view` - View entity details
- `cancel` - Cancel current operation
- `navigate` - Navigation (use with `data-dazzle-nav-target`)

---

### Messages

Mark feedback elements (validation errors, success messages, etc.).

```html
<!-- Validation error for specific field -->
<div
  data-dazzle-message="Task.title"
  data-dazzle-message-kind="validation"
>
  Title is required
</div>

<!-- Global success message -->
<div
  data-dazzle-message="global"
  data-dazzle-message-kind="success"
>
  Task created successfully
</div>

<!-- Global error message -->
<div
  data-dazzle-message="global"
  data-dazzle-message-kind="error"
>
  Failed to save task
</div>
```

**Message Kinds**:
- `validation` - Field validation error
- `error` - General error
- `success` - Success confirmation
- `warning` - Warning message
- `info` - Informational message

---

### Navigation

Mark navigation elements.

```html
<!-- Link to view -->
<a data-dazzle-nav="task_list">Tasks</a>
<a data-dazzle-nav="task_detail" data-dazzle-nav-params='{"id": "123"}'>View Task</a>

<!-- Breadcrumb -->
<nav data-dazzle-breadcrumb="true">
  <a data-dazzle-nav="home">Home</a>
  <a data-dazzle-nav="task_list">Tasks</a>
  <span data-dazzle-breadcrumb-current="true">Task Details</span>
</nav>
```

---

### Data Tables

Mark table elements for list views.

```html
<table data-dazzle-table="Task">
  <thead>
    <tr>
      <th data-dazzle-column="Task.title">Title</th>
      <th data-dazzle-column="Task.completed">Status</th>
    </tr>
  </thead>
  <tbody>
    <tr data-dazzle-row="Task" data-dazzle-entity-id="123">
      <td data-dazzle-cell="Task.title">My Task</td>
      <td data-dazzle-cell="Task.completed">Done</td>
    </tr>
  </tbody>
</table>
```

---

### Forms

Mark form containers.

```html
<form
  data-dazzle-form="Task"
  data-dazzle-form-mode="create"
>
  <!-- fields -->
</form>

<form
  data-dazzle-form="Task"
  data-dazzle-form-mode="edit"
  data-dazzle-entity-id="123"
>
  <!-- fields -->
</form>
```

**Form Modes**:
- `create` - Creating new entity
- `edit` - Editing existing entity
- `search` - Search/filter form

---

### Dialogs / Modals

Mark dialog elements.

```html
<div
  data-dazzle-dialog="confirm_delete"
  data-dazzle-dialog-open="true"
>
  <div data-dazzle-dialog-title>Confirm Delete</div>
  <div data-dazzle-dialog-content>Are you sure?</div>
  <div data-dazzle-dialog-actions>
    <button data-dazzle-action="confirm" data-dazzle-action-role="destructive">Delete</button>
    <button data-dazzle-action="cancel" data-dazzle-action-role="cancel">Cancel</button>
  </div>
</div>
```

---

### Loading States

Mark loading indicators.

```html
<div data-dazzle-loading="true">Loading...</div>
<div data-dazzle-loading="Task.list">Loading tasks...</div>
<button data-dazzle-action="Task.save" data-dazzle-loading="true" disabled>Saving...</button>
```

---

### Authentication Elements

Mark authentication-related UI elements for E2E testing.

```html
<!-- Login button (opens auth modal) -->
<button data-dazzle-auth-action="login">Sign In</button>

<!-- Logout button -->
<button data-dazzle-auth-action="logout">Sign Out</button>

<!-- User indicator (shown when logged in) -->
<div data-dazzle-auth-user="true" data-dazzle-persona="admin">
  Welcome, Admin
</div>

<!-- Auth modal container -->
<div id="dz-auth-modal" data-dazzle-dialog="auth">
  <form id="dz-auth-form">
    <input name="email" type="email" />
    <input name="password" type="password" />
    <input name="display_name" type="text" />  <!-- For registration -->
    <button id="dz-auth-submit" type="submit">Sign In</button>
  </form>
  <div id="dz-auth-error">Error message here</div>
</div>

<!-- Mode toggle (login/register) -->
<button data-dazzle-auth-toggle="register">Create Account</button>
<button data-dazzle-auth-toggle="login">Sign In</button>
```

**Authentication Attributes**:
- `data-dazzle-auth-action` - Auth action type (`login`, `logout`)
- `data-dazzle-auth-user` - Present when user is authenticated
- `data-dazzle-persona` - User's persona/role
- `data-dazzle-auth-toggle` - Switch between login/register modes

**Standard Auth Element IDs**:
- `#dz-auth-modal` - Auth modal container
- `#dz-auth-form` - Login/register form
- `#dz-auth-submit` - Form submit button
- `#dz-auth-error` - Error message display

---

## Attribute Reference Table

| Attribute | Values | Description |
|-----------|--------|-------------|
| `data-dazzle-view` | `{entity}_{mode}` | Current view identifier |
| `data-dazzle-entity` | Entity name | Entity type context |
| `data-dazzle-entity-id` | UUID/ID | Specific entity instance |
| `data-dazzle-field` | `{Entity}.{field}` | Input field identifier |
| `data-dazzle-field-type` | text, checkbox, etc. | Field input type |
| `data-dazzle-field-group` | `{Entity}.{field}` | Field container group |
| `data-dazzle-required` | true/false | Required field marker |
| `data-dazzle-label` | `{Entity}.{field}` | Label for field |
| `data-dazzle-action` | `{Entity}.{action}` | Action identifier |
| `data-dazzle-action-role` | primary, destructive, etc. | Action type |
| `data-dazzle-message` | `{Entity}.{field}` or `global` | Message target |
| `data-dazzle-message-kind` | validation, error, success | Message type |
| `data-dazzle-nav` | view name | Navigation target |
| `data-dazzle-nav-params` | JSON | Navigation parameters |
| `data-dazzle-table` | Entity name | Table for entity |
| `data-dazzle-column` | `{Entity}.{field}` | Table column |
| `data-dazzle-row` | Entity name | Table row |
| `data-dazzle-cell` | `{Entity}.{field}` | Table cell |
| `data-dazzle-form` | Entity name | Form for entity |
| `data-dazzle-form-mode` | create, edit, search | Form mode |
| `data-dazzle-dialog` | dialog name | Dialog identifier |
| `data-dazzle-dialog-open` | true/false | Dialog visibility |
| `data-dazzle-loading` | true or context | Loading state |
| `data-dazzle-auth-action` | login, logout | Auth action type |
| `data-dazzle-auth-user` | true | Present when authenticated |
| `data-dazzle-persona` | persona name | User's role/persona |
| `data-dazzle-auth-toggle` | login, register | Auth mode switch |

---

## Playwright Locator Examples

```typescript
// View
page.locator('[data-dazzle-view="task_list"]')

// Field input
page.locator('[data-dazzle-field="Task.title"]')

// Action button
page.locator('[data-dazzle-action="Task.create"]')

// Primary action on page
page.locator('[data-dazzle-action-role="primary"]')

// Validation error for field
page.locator('[data-dazzle-message="Task.title"][data-dazzle-message-kind="validation"]')

// Table row for specific entity
page.locator('[data-dazzle-row="Task"][data-dazzle-entity-id="123"]')

// Any loading indicator
page.locator('[data-dazzle-loading="true"]')
```

---

## Custom Events

DNR-UI dispatches standard `CustomEvent` events for cross-component communication and E2E testing hooks. All events are dispatched on `window` unless otherwise noted.

### Navigation Events

```typescript
// Event: dnr-navigate
// Triggered when navigation is requested
interface DnrNavigateEvent {
  detail: {
    url: string;               // Target URL path
    params?: Record<string, string>;  // Optional URL parameters
    replace?: boolean;         // Replace history instead of push
  }
}

// Example
window.addEventListener('dnr-navigate', (e) => {
  console.log('Navigate to:', e.detail.url);
});

// Dispatching
window.dispatchEvent(new CustomEvent('dnr-navigate', {
  detail: { url: '/task/123/edit' }
}));
```

### Entity CRUD Events

```typescript
// Event: dnr-delete
// Triggered when entity deletion is requested
interface DnrDeleteEvent {
  detail: {
    entity: string;            // Entity name (e.g., "Task")
    id: string | number;       // Entity ID
  }
}

// Event: dnr-create
// Triggered when entity creation is requested
interface DnrCreateEvent {
  detail: {
    entity: string;            // Entity name
    data?: Record<string, any>; // Initial data
  }
}

// Event: dnr-update
// Triggered when entity update is requested
interface DnrUpdateEvent {
  detail: {
    entity: string;            // Entity name
    id: string | number;       // Entity ID
    data: Record<string, any>; // Updated fields
  }
}

// Example
window.addEventListener('dnr-delete', async (e) => {
  const { entity, id } = e.detail;
  await fetch(`/api/${entity.toLowerCase()}/${id}`, { method: 'DELETE' });
});
```

### Authentication Events

```typescript
// Event: dnr-auth-login
// Triggered when login is successful
interface DnrAuthLoginEvent {
  detail: {
    user: {
      id: string;
      email: string;
      display_name?: string;
      persona?: string;
    }
  }
}

// Event: dnr-auth-logout
// Triggered when logout is requested or completed
interface DnrAuthLogoutEvent {
  detail: {
    reason?: 'user_action' | 'session_expired' | 'forced';
  }
}

// Event: dnr-auth-error
// Triggered when authentication fails
interface DnrAuthErrorEvent {
  detail: {
    error: string;             // Error message
    code?: string;             // Error code
  }
}
```

### Form Events

```typescript
// Event: dnr-form-submit
// Triggered when a form is submitted
interface DnrFormSubmitEvent {
  detail: {
    entity: string;            // Entity name
    mode: 'create' | 'edit';   // Form mode
    data: Record<string, any>; // Form data
    entityId?: string;         // ID if editing
  }
}

// Event: dnr-form-validate
// Triggered when validation is needed
interface DnrFormValidateEvent {
  detail: {
    entity: string;
    field?: string;            // Specific field or all
    value?: any;               // Field value
  }
}

// Event: dnr-form-error
// Triggered when form submission fails
interface DnrFormErrorEvent {
  detail: {
    entity: string;
    errors: Record<string, string>; // Field -> error message
    global?: string;           // Global error message
  }
}
```

### Data Loading Events

```typescript
// Event: dnr-data-loading
// Triggered when data fetch starts
interface DnrDataLoadingEvent {
  detail: {
    entity: string;
    context?: string;          // e.g., "list", "detail"
  }
}

// Event: dnr-data-loaded
// Triggered when data fetch completes
interface DnrDataLoadedEvent {
  detail: {
    entity: string;
    data: any;                 // Loaded data
    count?: number;            // Total count for lists
  }
}

// Event: dnr-data-error
// Triggered when data fetch fails
interface DnrDataErrorEvent {
  detail: {
    entity: string;
    error: string;
    status?: number;           // HTTP status code
  }
}
```

### Modal/Dialog Events

```typescript
// Event: dnr-modal-open
// Triggered when a modal opens
interface DnrModalOpenEvent {
  detail: {
    name: string;              // Modal identifier
    data?: any;                // Data passed to modal
  }
}

// Event: dnr-modal-close
// Triggered when a modal closes
interface DnrModalCloseEvent {
  detail: {
    name: string;
    result?: any;              // Result from modal
    action?: 'confirm' | 'cancel' | 'dismiss';
  }
}
```

### Event Reference Table

| Event | Detail Properties | Description |
|-------|------------------|-------------|
| `dnr-navigate` | `url`, `params?`, `replace?` | Navigation request |
| `dnr-delete` | `entity`, `id` | Entity deletion request |
| `dnr-create` | `entity`, `data?` | Entity creation request |
| `dnr-update` | `entity`, `id`, `data` | Entity update request |
| `dnr-auth-login` | `user` | Login success |
| `dnr-auth-logout` | `reason?` | Logout request/complete |
| `dnr-auth-error` | `error`, `code?` | Authentication failure |
| `dnr-form-submit` | `entity`, `mode`, `data`, `entityId?` | Form submission |
| `dnr-form-validate` | `entity`, `field?`, `value?` | Validation request |
| `dnr-form-error` | `entity`, `errors`, `global?` | Form errors |
| `dnr-data-loading` | `entity`, `context?` | Data fetch started |
| `dnr-data-loaded` | `entity`, `data`, `count?` | Data fetch complete |
| `dnr-data-error` | `entity`, `error`, `status?` | Data fetch failed |
| `dnr-modal-open` | `name`, `data?` | Modal opened |
| `dnr-modal-close` | `name`, `result?`, `action?` | Modal closed |

### Testing with Events

E2E tests can listen for these events to verify behavior:

```typescript
// Playwright example - wait for navigation
await page.evaluate(() => {
  return new Promise((resolve) => {
    window.addEventListener('dnr-navigate', (e) => resolve(e.detail), { once: true });
  });
});

// Verify delete event was dispatched
const deletePromise = page.evaluate(() => {
  return new Promise((resolve) => {
    window.addEventListener('dnr-delete', (e) => resolve(e.detail), { once: true });
  });
});

await page.click('[data-dazzle-action="Task.delete"]');
const deleteEvent = await deletePromise;
expect(deleteEvent.entity).toBe('Task');
```

---

## Implementation Requirements

All Dazzle builders (DNR, future stacks) MUST:

1. Emit these attributes on all interactive elements
2. Use consistent naming derived from AppSpec
3. Include entity context where applicable
4. Mark all actions with appropriate roles
5. Provide validation message containers even when empty
6. Dispatch standard events for navigation, CRUD, and auth operations

---

## Versioning

This contract is versioned. Breaking changes require a major version bump.

- **v1.0** (2025-11-29): Initial specification
- **v1.1** (2025-12-01): Added event schemas, authentication attributes
