# Component Showcase

A kitchen-sink gallery app for visual regression testing of all Dazzle UX components.

Every widget type is exercised on a single "Showcase" entity, making it easy to verify
all components render correctly from a single create/edit form.

## Widget Types Covered

- Plain text input
- Rich text editor (Quill)
- Textarea
- Select (enum)
- Combobox (Tom Select)
- Multi-select tags (Tom Select)
- Checkbox (boolean)
- Date picker (Flatpickr)
- DateTime picker (Flatpickr)
- Date range picker (Flatpickr)
- Color picker x2 (Pickr)
- Range slider x2
- Number input
- File upload

## Running

```bash
cd examples/component_showcase
dazzle serve --local
```

- UI: http://localhost:3000
- API: http://localhost:8000/docs

Navigate to "Create Showcase" to see all widget types on a single form.
