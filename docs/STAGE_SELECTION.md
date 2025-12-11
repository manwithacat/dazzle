# Stage Selection Guide

This guide explains how DAZZLE's semantic UI layout engine selects the optimal stage for each workspace based on its attention signals.

## Table of Contents
- [Overview](#overview)
- [The 5 Stages](#the-5-stages)
- [Selection Algorithm](#selection-algorithm)
- [Signal Weight Calculation](#signal-weight-calculation)
- [Examples](#examples)
- [Forcing an Stage](#forcing-an-stage)
- [Debugging Selection](#debugging-selection)
- [Common Patterns](#common-patterns)

---

## Overview

The stage selection algorithm analyzes your workspace's **attention signals** to determine the best UI pattern. Each signal has:
- **Kind**: KPI, TABLE, ITEM_LIST, CHART, DETAIL_VIEW, etc.
- **Weight**: Calculated based on features (filters, aggregates, limits)
- **Priority**: Implicit ranking based on kind and weight

The algorithm selects the stage that best matches your signal composition.

---

## The 5 Stages

### 1. FOCUS_METRIC
**Purpose**: Single dominant metric with minimal context

**Best For**:
- Uptime monitoring
- Revenue dashboards
- Critical KPIs
- Alert counts

**Characteristics**:
- 1 dominant KPI signal (weight ≥ 0.7)
- Optional supporting metrics
- Large, prominent display
- Minimal cognitive load

**Surfaces**:
- `hero`: Main KPI (capacity: 1.0, priority: 1)
- `context`: Supporting metrics (capacity: 0.4, priority: 2)

**Example**: System uptime percentage with service count

---

### 2. SCANNER_TABLE
**Purpose**: Dense, scannable data for rapid review

**Best For**:
- Admin panels
- Inventory management
- User lists
- Data browsing

**Characteristics**:
- 1 dominant TABLE signal (weight ≥ 0.6)
- Optional toolbar/filters
- Horizontal scrolling on mobile
- Compact, information-dense

**Surfaces**:
- `table`: Main data table (capacity: 1.0, priority: 1)
- `toolbar`: Filters/actions (capacity: 0.3, priority: 2)

**Example**: Product inventory with search and filters

---

### 3. DUAL_PANE_FLOW
**Purpose**: Master-detail pattern for browsing with context

**Best For**:
- Email clients
- Contact managers
- File browsers
- Item selection with details

**Characteristics**:
- 1 ITEM_LIST signal (weight ≥ 0.3)
- 1 DETAIL_VIEW signal (weight ≥ 0.3)
- List and detail both significant
- Responsive collapse on mobile

**Surfaces**:
- `list`: Item list (capacity: 0.6, priority: 1)
- `detail`: Selected item details (capacity: 0.8, priority: 2)

**Example**: Contact list with contact details pane

---

### 4. MONITOR_WALL
**Purpose**: Multiple balanced metrics for at-a-glance monitoring

**Best For**:
- Operations dashboards
- Multi-metric monitoring
- System health overviews
- Balanced information needs

**Characteristics**:
- 3-8 signals
- No single dominant signal
- Balanced weight distribution
- Grid layout

**Surfaces**:
- `grid_primary`: Higher priority signals (capacity: 1.2, priority: 1)
- `grid_secondary`: Supporting signals (capacity: 0.8, priority: 2)
- `sidebar`: Optional tertiary info (capacity: 0.4, priority: 3)

**Example**: Email inbox with unread count, urgent items, flagged items, recent emails

---

### 5. COMMAND_CENTER
**Purpose**: High-density expert interface for power users

**Best For**:
- Trading platforms
- Network operations centers
- Complex workflows
- Expert users

**Characteristics**:
- 9+ signals OR high total complexity
- Dense information display
- Multiple data sources
- Expert-level interface

**Surfaces**:
- `primary_grid`: Main signals (capacity: 1.5, priority: 1)
- `secondary_grid`: Supporting signals (capacity: 1.0, priority: 2)
- `sidebar`: Auxiliary info (capacity: 0.5, priority: 3)
- `footer`: Status/notifications (capacity: 0.3, priority: 4)

**Example**: Operations dashboard with 10+ metrics and alerts

---

## Selection Algorithm

The stage is selected using this priority-based decision tree:

```
1. Check for dominant KPI
   IF max_kpi_weight ≥ 0.7 → FOCUS_METRIC

2. Check for dominant table
   IF total_table_weight ≥ 0.6 → SCANNER_TABLE

3. Check for list + detail combination
   IF list_weight ≥ 0.3 AND detail_weight ≥ 0.3 → DUAL_PANE_FLOW

4. Check signal count
   IF signal_count ≥ 9 → COMMAND_CENTER
   IF 3 ≤ signal_count ≤ 8 → MONITOR_WALL

5. Default fallback
   → MONITOR_WALL
```

### Selection Code
Location: `src/dazzle/ui/layout_engine/select_stage.py`

```python
def select_stage(layout: WorkspaceLayout) -> Stage:
    """Select optimal stage based on attention signals."""

    # Calculate signal weights by kind
    weights = calculate_signal_weights(layout.attention_signals)

    # Priority 1: Dominant KPI
    if weights['kpi'] >= 0.7:
        return Stage.FOCUS_METRIC

    # Priority 2: Dominant table
    if weights['table'] >= 0.6:
        return Stage.SCANNER_TABLE

    # Priority 3: List + detail
    if weights['list'] >= 0.3 and weights['detail'] >= 0.3:
        return Stage.DUAL_PANE_FLOW

    # Priority 4: Signal count
    signal_count = len(layout.attention_signals)
    if signal_count >= 9:
        return Stage.COMMAND_CENTER
    if 3 <= signal_count <= 8:
        return Stage.MONITOR_WALL

    # Default
    return Stage.MONITOR_WALL
```

---

## Signal Weight Calculation

Each attention signal's weight is calculated based on its features:

### Base Weight
```
Base weight = 0.5
```

### Weight Modifiers
```
+ 0.2  if signal has filters
+ 0.1  if signal has limit
+ 0.2  if signal has aggregates
+ 0.2  if signal has display: detail
```

### Examples

**Simple KPI** (no features):
```dsl
uptime_percentage:
  source: Service
  # Weight = 0.5 (base only)
```

**KPI with aggregates** (FOCUS_METRIC trigger):
```dsl
system_uptime:
  source: Service
  aggregate:
    avg_uptime: avg(uptime_percentage)
    total_services: count(Service)
  # Weight = 0.5 + 0.2 = 0.7 ✓ (triggers FOCUS_METRIC)
```

**Table with filters**:
```dsl
all_products:
  source: Product
  where: active = true
  limit: 100
  # Weight = 0.5 + 0.2 + 0.1 = 0.8 (strong TABLE signal)
```

**Detail view**:
```dsl
contact_detail:
  source: Contact
  display: detail
  # Weight = 0.5 + 0.2 = 0.7 (strong DETAIL_VIEW)
```

---

## Examples

### Example 1: FOCUS_METRIC (Uptime Monitor)

**DSL**:
```dsl
workspace uptime "System Uptime":
  purpose: "Monitor overall system availability"

  system_uptime:
    source: Service
    aggregate:
      average_uptime: avg(uptime_percentage)
      total_services: count(Service)
      services_down: count(Service WHERE status = 'down')
```

**Calculation**:
- `system_uptime` signal
  - Kind: KPI (inferred from aggregates)
  - Weight: 0.5 (base) + 0.2 (aggregates) = **0.7**
- Total signals: 1

**Selection**: `max_kpi_weight = 0.7 ≥ 0.7` → **FOCUS_METRIC** ✓

**Surfaces Allocated**:
- `hero`: system_uptime (100% of capacity)

---

### Example 2: SCANNER_TABLE (Inventory Scanner)

**DSL**:
```dsl
workspace inventory "Inventory":
  purpose: "Browse all products"

  all_products:
    source: Product
    where: in_stock = true
    limit: 100
```

**Calculation**:
- `all_products` signal
  - Kind: TABLE (inferred from source with limit)
  - Weight: 0.5 (base) + 0.2 (filter) + 0.1 (limit) = **0.8**
- Total signals: 1

**Selection**: `total_table_weight = 0.8 ≥ 0.6` → **SCANNER_TABLE** ✓

**Surfaces Allocated**:
- `table`: all_products (100% of capacity)

---

### Example 3: DUAL_PANE_FLOW (Contact Manager)

**DSL**:
```dsl
workspace contacts "Contacts":
  purpose: "Browse and view contacts"

  contact_list:
    source: Contact
    limit: 20
    # Weight = 0.5 + 0.1 = 0.6

  contact_detail:
    source: Contact
    display: detail
    # Weight = 0.5 + 0.2 = 0.7
```

**Calculation**:
- `contact_list`: ITEM_LIST, weight = 0.6
- `contact_detail`: DETAIL_VIEW, weight = 0.7

**Selection**: `list_weight = 0.6 ≥ 0.3 AND detail_weight = 0.7 ≥ 0.3` → **DUAL_PANE_FLOW** ✓

**Surfaces Allocated**:
- `list`: contact_list
- `detail`: contact_detail

---

### Example 4: MONITOR_WALL (Email Client)

**DSL**:
```dsl
workspace inbox "Inbox":
  purpose: "Email overview"

  unread_count:
    source: Email
    aggregate:
      unread: count(Email WHERE is_read = false)
    # Weight = 0.5 + 0.2 = 0.7 (KPI)

  urgent_emails:
    source: Email
    where: priority = 'urgent'
    limit: 5
    # Weight = 0.5 + 0.2 + 0.1 = 0.8 (ITEM_LIST)

  flagged_items:
    source: Email
    where: is_flagged = true
    limit: 10
    # Weight = 0.5 + 0.2 + 0.1 = 0.8 (ITEM_LIST)

  all_emails:
    source: Email
    limit: 50
    # Weight = 0.5 + 0.1 = 0.6 (TABLE)
```

**Calculation**:
- 4 signals total
- `max_kpi_weight = 0.7` (not ≥ 0.7, but close)
- `total_table_weight = 0.6` (not ≥ 0.6, close)
- `list_weight = 0.8`, `detail_weight = 0` (no detail)
- `signal_count = 4` (in range 3-8)

**Selection**: `3 ≤ signal_count ≤ 8` → **MONITOR_WALL** ✓

**Surfaces Allocated**:
- `grid_primary`: unread_count, urgent_emails
- `grid_secondary`: flagged_items, all_emails

---

### Example 5: COMMAND_CENTER (Ops Dashboard)

**DSL**:
```dsl
workspace operations "Operations Center":
  purpose: "Monitor all systems"

  # 10 different signals (CPU, memory, disk, network, errors, etc.)
  # Each with varying weights
```

**Calculation**:
- 10 signals total
- No single dominant signal

**Selection**: `signal_count = 10 ≥ 9` → **COMMAND_CENTER** ✓

**Surfaces Allocated**:
- `primary_grid`: Top 6 signals by weight
- `secondary_grid`: Remaining 4 signals
- `sidebar`: Optional auxiliary data

---

## Forcing an Stage

You can override automatic selection using `stage`:

```dsl
workspace dashboard "Dashboard":
  purpose: "Custom layout"
  stage: "dual_pane_flow"  # Force specific stage

  # Your signals...
```

**Valid Values**:
- `"focus_metric"`
- `"scanner_table"`
- `"dual_pane_flow"`
- `"monitor_wall"`
- `"command_center"`

**When to Use**:
- UX consistency across workspaces
- Experimentation with different layouts
- Override when algorithm selects wrong pattern

**Location**: `src/dazzle/core/ir.py:WorkspaceSpec.stage`

---

## Debugging Selection

### View Selected Stage

Use the generated workspace page to see the selected stage:

```typescript
// src/app/workspace-name/page.tsx
const layoutPlan: LayoutPlan = {
  stage: Stage.FOCUS_METRIC,  // ← Selected stage
  surfaces: [...],
  // ...
};
```

### Check Signal Weights

Add debug output in converter:

```python
# src/dazzle/ui/layout_engine/converter.py
layout = convert_workspace_to_layout(workspace_spec)

# Debug: Print signal weights
for signal in layout.attention_signals:
    print(f"{signal.id}: kind={signal.kind.value}, weight={signal.attention_weight}")
```

### Verify Selection Logic

Run the selection algorithm manually:

```python
from dazzle.ui.layout_engine.select_stage import select_stage

stage = select_stage(layout)
print(f"Selected: {stage.value}")
```

### Common Issues

**Issue**: Expected FOCUS_METRIC but got MONITOR_WALL
**Cause**: KPI weight < 0.7
**Fix**: Add aggregates to boost weight to ≥ 0.7

**Issue**: Expected DUAL_PANE_FLOW but got SCANNER_TABLE
**Cause**: Missing `display: detail` on detail signal
**Fix**: Add `display: detail` to detail view signal

**Issue**: Expected SCANNER_TABLE but got MONITOR_WALL
**Cause**: Table weight < 0.6 or multiple signals
**Fix**: Ensure single table with filters/limit, or use `stage`

---

## Common Patterns

### Pattern 1: Single Critical Metric
```dsl
workspace metrics:
  main_kpi:
    source: Data
    aggregate:
      value: sum(amount)
```
**→ FOCUS_METRIC**

### Pattern 2: Data Browsing
```dsl
workspace browse:
  all_items:
    source: Item
    limit: 100
```
**→ SCANNER_TABLE**

### Pattern 3: Master-Detail
```dsl
workspace manager:
  item_list:
    source: Item
    limit: 20

  item_detail:
    source: Item
    display: detail
```
**→ DUAL_PANE_FLOW**

### Pattern 4: Multiple Metrics
```dsl
workspace dashboard:
  metric1: ...
  metric2: ...
  metric3: ...
  metric4: ...
```
**→ MONITOR_WALL** (3-8 signals)

### Pattern 5: Expert Interface
```dsl
workspace control:
  # 10+ signals with various kinds
```
**→ COMMAND_CENTER** (9+ signals)

---

## Summary

**Selection Priority**:
1. Dominant KPI (≥ 0.7) → FOCUS_METRIC
2. Dominant table (≥ 0.6) → SCANNER_TABLE
3. List + detail → DUAL_PANE_FLOW
4. 9+ signals → COMMAND_CENTER
5. 3-8 signals → MONITOR_WALL
6. Default → MONITOR_WALL

**Key Takeaways**:
- Signal weight is calculated from features (filters, aggregates, limits)
- Stage selection is deterministic and priority-based
- Use `stage` to override when needed
- Test with different signal compositions to explore stages

**References**:
- Code: `src/dazzle/ui/layout_engine/select_stage.py`
- Examples: `examples/` directory
- Tests: `tests/integration/test_stage_examples.py`
