# Contact Manager - DUAL_PANE_FLOW Example

This example demonstrates the **DUAL_PANE_FLOW** archetype, which provides a master-detail interface for browsing items and viewing detailed information.

## Archetype: DUAL_PANE_FLOW

**Purpose**: Browse list of items while viewing details of selected item

**Best For**:
- Contact managers
- Email clients
- File browsers
- Item catalogs with details

## Features

### Entity: Contact
- Personal information (name, email, phone)
- Professional details (company, job title)
- Notes and favorites
- Automatic timestamps

### Workspace: Contacts
Two complementary signals create the dual-pane interface:

1. **contact_list** (ITEM_LIST signal)
   - Displays all contacts in a browsable list
   - Sorted alphabetically by last name, first name
   - Limited to 20 items for performance
   - Weight: 0.6 (base 0.5 + limit 0.1)

2. **contact_detail** (DETAIL_VIEW signal)
   - Shows full details of selected contact
   - Uses new `display: detail` syntax (v0.3.0)
   - Weight: 0.7 (base 0.5 + detail 0.2)

## Archetype Selection

**Why DUAL_PANE_FLOW?**

The selection algorithm checks:
- ✅ list_weight (0.6) ≥ 0.3
- ✅ detail_weight (0.7) ≥ 0.3
- Result: **DUAL_PANE_FLOW** archetype

**Alternative Archetypes**:
- If only contact_list: **SCANNER_TABLE** (single table)
- If 3+ additional signals: **MONITOR_WALL** (multiple metrics)

## UI Layout

### Desktop
```
┌─────────────────────────────────────────┐
│ Contacts                                │
├──────────────┬──────────────────────────┤
│ Contact List │ Contact Details          │
│              │                          │
│ □ Alice A.   │ Alice Anderson           │
│ ■ Bob B.     │ alice@example.com        │
│ □ Carol C.   │ (555) 123-4567          │
│ □ Dave D.    │                          │
│ ...          │ Company: Acme Corp       │
│              │ Title: Engineer          │
│              │                          │
│              │ Notes:                   │
│              │ Team lead for project X  │
└──────────────┴──────────────────────────┘
```

### Mobile
```
┌────────────────┐     ┌────────────────┐
│ Contacts       │  →  │ ← Back         │
│                │     │                │
│ □ Alice A.     │     │ Alice Anderson │
│ ■ Bob B.       │     │                │
│ □ Carol C.     │     │ alice@ex...    │
│ □ Dave D.      │     │ (555) 123-4567│
│ ...            │     │                │
│                │     │ Company:       │
│                │     │ Acme Corp      │
│                │     │                │
│                │     │ Title:         │
│                │     │ Engineer       │
└────────────────┘     └────────────────┘
  List view            Detail slides over
```

## Surface Allocation

| Surface | Capacity | Priority | Assigned Signal | Description |
|---------|----------|----------|-----------------|-------------|
| list    | 0.6      | 1        | contact_list    | Browsable contact list |
| detail  | 0.8      | 2        | contact_detail  | Selected contact details |

## Generated Components

### Archetype Component
- **DualPaneFlow.tsx**: Master-detail layout with responsive behavior
  - Desktop: Side-by-side panes (30% list, 70% detail)
  - Tablet: Adjustable split
  - Mobile: Stacked with slide-over detail

### Surfaces
- **List Pane**: Navigation sidebar with scrollable contact list
- **Detail Pane**: Main content area with selected contact info

## Building

```bash
# Validate DSL
dazzle validate

# Generate Next.js app
dazzle build --stack nextjs_semantic

# View output
cd build/contact-manager
npm install
npm run dev
```

## Try It

1. **Change to SCANNER_TABLE**:
   ```dsl
   # Remove contact_detail signal
   # Keep only contact_list
   ```
   Result: Full-width table view

2. **Change to MONITOR_WALL**:
   ```dsl
   # Add more signals (recent contacts, favorites, etc.)
   ```
   Result: Grid layout with multiple metrics

3. **Force archetype**:
   ```dsl
   workspace contacts:
     engine_hint: "scanner_table"  # Override to table view
   ```

## Key Learnings

1. **display: detail is essential** for DUAL_PANE_FLOW
   - Creates DETAIL_VIEW signal with +0.2 weight
   - Without it, algorithm selects different archetype

2. **Both signals must be significant**
   - list_weight ≥ 0.3 AND detail_weight ≥ 0.3
   - Ensures balanced master-detail interface

3. **Responsive by default**
   - Desktop: Side-by-side
   - Mobile: Stacked with transitions
   - No custom CSS needed

## References

- Archetype Guide: [docs/ARCHETYPE_SELECTION.md](../../docs/ARCHETYPE_SELECTION.md)
- DSL Reference: [docs/DAZZLE_DSL_REFERENCE_0_1.md](../../docs/DAZZLE_DSL_REFERENCE_0_1.md)
- Tests: [tests/integration/test_archetype_examples.py](../../tests/integration/test_archetype_examples.py)
