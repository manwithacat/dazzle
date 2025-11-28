# Archetype Showcase

This example demonstrates all five DNR layout archetypes, each designed for specific use cases.

## Archetypes

### 1. FOCUS_METRIC
**Use case**: Single dominant KPI display

Best for dashboards where one metric is the primary focus (e.g., revenue, uptime percentage, active users).

```
┌─────────────────────────────────┐
│         HERO METRIC             │
│           $1.2M                 │
│         ▲ 12.3%                 │
├─────────┬─────────┬─────────────┤
│ Support │ Support │ Supporting  │
│ Metric1 │ Metric2 │ Metrics...  │
└─────────┴─────────┴─────────────┘
```

### 2. SCANNER_TABLE
**Use case**: Dense table with filtering

Best for data-heavy views where scanning and filtering are primary actions (e.g., inventory lists, user management, logs).

```
┌─────────────────────────────────┐
│ Filters: [Category▼] [Status▼]  │
├─────────────────────────────────┤
│ SKU    │ Name    │ Qty │ Status│
│ ABC001 │ Item A  │ 50  │ ✓     │
│ ABC002 │ Item B  │ 0   │ ✗     │
│ ABC003 │ Item C  │ 25  │ ✓     │
│ ...    │ ...     │ ... │ ...   │
└─────────────────────────────────┘
```

### 3. DUAL_PANE_FLOW
**Use case**: List + Detail master-detail

Best for browse-and-view workflows where users select from a list and see details (e.g., email clients, task managers, document browsers).

```
┌──────────────┬──────────────────┐
│   LIST       │     DETAIL       │
│ ○ Task 1     │ Task 2           │
│ ● Task 2     │ ─────────────    │
│ ○ Task 3     │ Description...   │
│ ○ Task 4     │ Status: Active   │
│ ...          │ Due: Tomorrow    │
└──────────────┴──────────────────┘
```

### 4. MONITOR_WALL
**Use case**: Grid of moderate-importance signals

Best for monitoring dashboards where multiple metrics have similar importance (e.g., server status, application metrics, sales KPIs).

```
┌─────────┬─────────┬─────────────┐
│ Service │ Service │ Service     │
│ Status  │ Uptime  │ Response    │
├─────────┼─────────┼─────────────┤
│ Alert 1 │ Alert 2 │ Performance │
│ Alert 3 │ Metric  │ Graphs      │
└─────────┴─────────┴─────────────┘
```

### 5. COMMAND_CENTER
**Use case**: Dense, expert-focused dashboard

Best for operations centers where expert users need access to many signals at once (e.g., NOC dashboards, trading floors, incident response).

```
┌─────────┬───────────────────────┐
│CRITICAL │ SERVICE HEALTH GRID   │
│ALERTS   │ ● ● ● ○ ● ● ○ ●      │
│ Alert 1 ├───────────────────────┤
│ Alert 2 │ ACTIVE    │ PENDING   │
│ Alert 3 │ Task 1    │ Task A    │
├─────────┤ Task 2    │ Task B    │
│ METRICS │ Task 3    │ Task C    │
│ KPI1 42 ├───────────────────────┤
│ KPI2 87 │ RECENT ALERTS         │
│ KPI3 23 │ ⚠ Warning at 10:30   │
└─────────┴───────────────────────┘
```

## Usage

```bash
# Validate the DSL
cd examples/archetype_showcase
dazzle validate

# Generate UI preview
dazzle dnr build-ui --format html -o ./preview
open ./preview/index.html

# Generate full Vite project
dazzle dnr build-ui --format vite -o ./app
cd app
npm install
npm run dev
```

## Archetype Selection

The layout engine automatically selects archetypes based on:

1. **Dominant KPI** (attention weight > 0.7) → FOCUS_METRIC
2. **Strong table weight** (> 0.6) → SCANNER_TABLE
3. **List + detail** pattern → DUAL_PANE_FLOW
4. **High diversity + many signals** (5+) → COMMAND_CENTER
5. **Multiple moderate signals** (3-8) → MONITOR_WALL

You can override with `engine_hint` in your workspace:

```dsl
workspace dashboard "Dashboard":
    engine_hint: "focus_metric"
    ...
```

## See Also

- [DNR Documentation](../../docs/dnr/README.md)
- [Archetype Selection Algorithm](../../docs/ARCHETYPE_SELECTION.md)
