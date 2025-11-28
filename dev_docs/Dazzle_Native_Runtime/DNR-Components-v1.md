# DNR-Components-v1

This document defines an initial registry of **DNR primitive components** and **pattern components** for the Dazzle Native UI Runtime (DNR-UI).

The goal is to provide a small, stable vocabulary of semantic UI atoms that:

- Are easy for an LLM to discover and reason about.
- Are token-efficient to refer to.
- Can be implemented by the DazzleUI runtime using any underlying UI toolkit.
- Can be composed to cover common SaaS / dashboard-style products.

All components are represented in UISpec as `ComponentSpec` with a `propsSchema` (expressed below in TypeScript-like notation for clarity).

---

## 1. Primitive Components

Primitive components are the core atoms rendered by the DazzleUI runtime. Pattern components (section 2) are defined purely in terms of these primitives.

### 1.1 Page

A top-level visual container for a logical screen within a workspace.

```ts
type PageProps = {
  title?: string;
  subtitle?: string;
  actions?: ActionButtonDef[]; // e.g., primary CTA(s)
  children: ViewNode[];
};

type ActionButtonDef = {
  label: string;
  action: string;        // ActionSpec.name
  variant?: "primary" | "secondary" | "ghost" | "danger";
};
```

### 1.2 LayoutShell

Generic shell arranging header/sidebar/content.

```ts
type LayoutShellProps = {
  header?: ViewNode;
  sidebar?: ViewNode;
  main: ViewNode;
  footer?: ViewNode;
  variant?: "appShell" | "centered" | "split";
};
```

### 1.3 Card

Used to group related content visually.

```ts
type CardProps = {
  title?: string;
  subtitle?: string;
  actions?: ActionButtonDef[];
  children: ViewNode[];
  variant?: "default" | "outlined" | "ghost" | "danger";
};
```

### 1.4 DataTable

Featureful table for tabular data.

```ts
type DataTableColumnDef = {
  id: string;
  label: string;
  accessor: string; // path into row object, e.g. "client.name"
  sortable?: boolean;
  align?: "left" | "right" | "center";
  width?: "auto" | "stretch" | number;
};

type DataTableProps = {
  rows: any[]; // typically bound from state
  columns: DataTableColumnDef[];
  keyField?: string; // unique key in each row
  pageSize?: number;
  enableSelection?: boolean;
  onRowClick?: string; // ActionSpec.name
  onSelectionChange?: string; // ActionSpec.name
  emptyStateMessage?: string;
};
```

### 1.5 SimpleTable

Minimal table for static/tabular layout when DataTable is overkill.

```ts
type SimpleTableProps = {
  headers: string[];
  rows: any[][];
};
```

### 1.6 Form

Container for form fields and submit/cancel actions.

```ts
type FormProps = {
  title?: string;
  fields: FieldDef[];
  submitLabel?: string;
  cancelLabel?: string;
  onSubmit: string; // ActionSpec.name
  onCancel?: string;
  layout?: "vertical" | "horizontal" | "twoColumn";
};

type FieldDef = {
  name: string;
  label: string;
  type: "text" | "textarea" | "number" | "select" | "checkbox" | "date" | "datetime";
  placeholder?: string;
  options?: { value: string; label: string }[]; // for select
  required?: boolean;
  helpText?: string;
};
```

### 1.7 Button

Primary clickable action control.

```ts
type ButtonProps = {
  label: string;
  action: string; // ActionSpec.name
  variant?: "primary" | "secondary" | "ghost" | "danger" | "link";
  size?: "sm" | "md" | "lg";
  iconLeft?: string;
  iconRight?: string;
  disabled?: boolean;
};
```

### 1.8 IconButton

Compact icon-only button.

```ts
type IconButtonProps = {
  icon: string;
  action: string;
  label?: string; // for accessibility
  variant?: "ghost" | "primary" | "danger";
};
```

### 1.9 Tabs and TabPanel

Tabbed navigation for sibling views.

```ts
type TabsProps = {
  value: string; // current tab id
  onChange: string; // ActionSpec.name
  tabs: { id: string; label: string }[];
};

type TabPanelProps = {
  tabId: string;
  children: ViewNode[];
};
```

### 1.10 Modal

Centered overlay dialog.

```ts
type ModalProps = {
  title?: string;
  open: boolean;
  onClose: string; // ActionSpec.name
  children: ViewNode[];
  size?: "sm" | "md" | "lg";
};
```

### 1.11 Drawer

Side panel overlay (e.g., from right).

```ts
type DrawerProps = {
  title?: string;
  open: boolean;
  onClose: string;
  position?: "left" | "right";
  children: ViewNode[];
};
```

### 1.12 Toolbar

Row of actions and controls (e.g., above a DataTable).

```ts
type ToolbarProps = {
  title?: string;
  children: ViewNode[];
  align?: "spaceBetween" | "left" | "right";
};
```

### 1.13 FilterBar

Quick filters above tables or lists.

```ts
type FilterDef = {
  field: string;
  label: string;
  type: "search" | "select" | "multiSelect" | "dateRange" | "tag";
  options?: { value: string; label: string }[];
};

type FilterBarProps = {
  filters: FilterDef[];
  onChange: string; // ActionSpec.name, receives filter state
};
```

### 1.14 SearchBox

Single search input with debounce.

```ts
type SearchBoxProps = {
  placeholder?: string;
  initialValue?: string;
  onSearch: string; // ActionSpec.name
};
```

### 1.15 MetricTile and MetricRow

Simple KPI metrics.

```ts
type MetricTileProps = {
  label: string;
  value: string | number;
  trend?: "up" | "down" | "flat";
  trendLabel?: string;
  variant?: "default" | "success" | "warning" | "danger";
};

type MetricRowProps = {
  metrics: MetricTileProps[];
};
```

### 1.16 SideNav and TopNav

Navigation primitives.

```ts
type NavItem = {
  label: string;
  route: string;
  icon?: string;
};

type SideNavProps = {
  items: NavItem[];
  activeRoute: string;
};

type TopNavProps = {
  items: NavItem[];
  activeRoute: string;
};
```

### 1.17 Breadcrumbs

Hierarchical navigation indicator.

```ts
type BreadcrumbsProps = {
  items: { label: string; route?: string }[];
};
```

---

## 2. Pattern Components

Pattern components are defined in UISpec purely as compositions of primitive components. They provide higher-level “lego blocks” for common SaaS patterns and can be expanded or overridden by the LLM, but are expected to remain semantically stable.

### 2.1 FilterableTable

A `DataTable` with an attached `FilterBar`, optionally wrapped in a `Card`.

```ts
type FilterableTableProps = {
  title?: string;
  columns: DataTableColumnDef[];
  filters: FilterDef[];
  dataStatePath: string;        // e.g., "workspace.clients"
  onFilterChange: string;       // ActionSpec.name
  onRowClick?: string;
};
```

### 2.2 SearchableList

List or table with a `SearchBox` and optional `FilterBar`.

```ts
type SearchableListProps = {
  title?: string;
  itemLabelField: string;       // path for label
  dataStatePath: string;
  onSearch: string;
  filters?: FilterDef[];
};
```

### 2.3 MasterDetailLayout

Master list on the left, detail panel on the right.

```ts
type MasterDetailLayoutProps = {
  masterComponent: string;      // ComponentSpec.name, e.g. "ClientList"
  detailComponent: string;      // ComponentSpec.name, e.g. "ClientDetail"
  initialDetailEmptyState?: string;
};
```

### 2.4 WizardForm

Multi-step form workflow.

```ts
type WizardStepDef = {
  id: string;
  title: string;
  description?: string;
  fields: FieldDef[];
};

type WizardFormProps = {
  steps: WizardStepDef[];
  initialStepId: string;
  onFinish: string;
  onCancel?: string;
};
```

### 2.5 CRUDPage

Basic CRUD page for a single entity: list + create/edit form.

```ts
type CRUDPageProps = {
  entityName: string;           // "Client", "Invoice"
  listComponent?: string;       // ComponentSpec.name (defaults to FilterableTable)
  formComponent?: string;       // ComponentSpec.name (defaults to Form)
  createService: string;        // ServiceSpec.name
  updateService: string;
  deleteService?: string;
};
```

### 2.6 MetricsDashboard

Simple overview page with a row of metrics and optional charts.

```ts
type MetricsDashboardProps = {
  title?: string;
  metrics: MetricTileProps[];
  secondaryComponents?: string[]; // e.g. "RevenueByMonthChart"
};
```

### 2.7 SettingsFormPage

Single-page settings panel.

```ts
type SettingsFormPageProps = {
  title?: string;
  description?: string;
  sections: {
    id: string;
    title: string;
    fields: FieldDef[];
  }[];
  loadService: string;
  saveService: string;
};
```

---

## 3. Registry & MCP Integration (Sketch)

Within the DNR-UI runtime, these components should be registered in a **ComponentRegistry**:

```ts
type ComponentRegistry = {
  primitives: ComponentSpec[];
  patterns: ComponentSpec[];
};
```

An MCP server for Dazzle can expose:

- `list_dnr_components` → returns primitive + pattern component metadata.
- `get_dnr_component_spec(name: string)` → returns full `ComponentSpec`.
- `list_dnr_patterns` → returns pattern components only.
- `instantiate_pattern(name: string, props: any)` → returns a `ComponentSpec` instance wired for a specific entity/workspace.

This allows an LLM agent to:

1. Discover available atoms (primitives/patterns).
2. Choose appropriate components by name.
3. Generate or patch UISpec using short, semantic references rather than verbose framework code.

End of DNR-Components-v1.
