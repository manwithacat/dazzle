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

## Implementation Requirements

All Dazzle builders (DNR, future stacks) MUST:

1. Emit these attributes on all interactive elements
2. Use consistent naming derived from AppSpec
3. Include entity context where applicable
4. Mark all actions with appropriate roles
5. Provide validation message containers even when empty

---

## Versioning

This contract is versioned. Breaking changes require a major version bump.

- **v1.0** (2025-11-29): Initial specification
