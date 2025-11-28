# DAZZLE Troubleshooting Guide

This guide helps diagnose and fix common issues when working with DAZZLE's semantic UI layout engine.

## Table of Contents
- [DSL Parsing Errors](#dsl-parsing-errors)
- [Reserved Keyword Conflicts](#reserved-keyword-conflicts)
- [Archetype Selection Issues](#archetype-selection-issues)
- [Attention Budget Problems](#attention-budget-problems)
- [Module Linking Errors](#module-linking-errors)
- [Validation Errors](#validation-errors)
- [Code Generation Issues](#code-generation-issues)

---

## DSL Parsing Errors

### Error: "Expected DEDENT, got <token>"

**Symptom**:
```
ParseError: Expected DEDENT, got order_by
  at dsl/app.dsl:34:5
```

**Cause**: Invalid syntax in workspace region. Workspace regions only support specific directives.

**Valid Workspace Region Directives**:
- `source: <entity_name>` (required)
- `limit: <number>`
- `where: <condition>`
- `aggregate: { ... }`
- `display: <mode>` (detail, card, table, etc.)

**Invalid Directives** (not supported in regions):
- ❌ `order_by` - Not supported in workspace regions
- ❌ `fields` - Not supported (use surface instead)
- ❌ `actions` - Not supported in workspace regions

**Fix**:
```dsl
# Before (ERROR):
contact_list:
  source: Contact
  order_by: last_name asc, first_name asc  # ❌ Not supported

# After (FIXED):
contact_list:
  source: Contact
  limit: 20  # ✓ Valid
```

**Reference**: See `docs/v0.2/DAZZLE_DSL_REFERENCE.md` for complete workspace region syntax.

---

### Error: "Invalid indentation"

**Symptom**:
```
ParseError: Invalid indentation at line 15
```

**Cause**: DAZZLE DSL uses strict indentation (2 spaces per level).

**Rules**:
1. Use exactly 2 spaces per indentation level
2. No tabs allowed (convert tabs to spaces)
3. Each nested block must be indented exactly 2 spaces
4. All lines in a block must have same indentation

**Fix**:
```dsl
# Before (ERROR):
workspace dashboard:
   purpose: "Monitor system"  # ❌ 3 spaces (inconsistent)

  uptime_metric:
    source: Service  # ❌ Mixed indentation

# After (FIXED):
workspace dashboard:
  purpose: "Monitor system"  # ✓ 2 spaces

  uptime_metric:
    source: Service  # ✓ 4 spaces (2 levels)
```

**Tip**: Configure your editor to use 2 spaces for `.dsl` files:
```json
// VS Code settings.json
{
  "[dazzle]": {
    "editor.tabSize": 2,
    "editor.insertSpaces": true
  }
}
```

---

### Error: "Unexpected token"

**Symptom**:
```
ParseError: Unexpected token 'constraint' at line 12
```

**Cause**: Using reserved keywords as identifiers.

**Solution**: Check `docs/DSL_RESERVED_KEYWORDS.md` for reserved words and use alternatives.

**Common Reserved Keywords**:
- Field names: `url`, `source`, `error`, `warning`, `limit`, `where`
- Use alternatives: `endpoint`, `data_source`, `err`, `warn`, `max_count`, `filter`

**Fix**:
```dsl
# Before (ERROR):
entity Config:
  url: str  # ❌ 'url' is reserved

# After (FIXED):
entity Config:
  endpoint: str  # ✓ Use alternative name
```

---

## Reserved Keyword Conflicts

### Issue: Reserved field name prevents entity creation

**Symptom**: Entity validation fails with "reserved keyword" error.

**Reserved Field Names**:
- `url` → Use: `endpoint`, `uri`, `address`
- `source` → Use: `data_source`, `event_source`, `origin`
- `error` → Use: `err`, `failure`, `fault`
- `warning` → Use: `warn`, `alert`, `caution`
- `limit` → Use: `max_count`, `max_items`, `cap`
- `where` → Use: `location`, `place`, `position`

**Reserved Enum Values**:
- `error` → Use: `err`, `failed`, `fault`
- `warning` → Use: `warn`, `alert`, `caution`
- `pending` → Use: `awaiting`, `queued`, `scheduled`

**Fix**:
```dsl
# Before (ERROR):
entity Alert:
  level: enum("info", "warning", "error")  # ❌ Reserved values

# After (FIXED):
entity Alert:
  level: enum("info", "warn", "err")  # ✓ Use alternatives
```

**Reference**: Complete list in `docs/DSL_RESERVED_KEYWORDS.md`.

---

## Archetype Selection Issues

### Issue: Expected FOCUS_METRIC but got MONITOR_WALL

**Symptom**: Workspace selects MONITOR_WALL archetype when you expected FOCUS_METRIC.

**Diagnosis**:
```bash
# Check signal weights
dazzle layout-plan

# Look for:
# KPI signal weight: must be >= 0.7 for FOCUS_METRIC
```

**Cause**: KPI signal weight < 0.7 (threshold for FOCUS_METRIC).

**Signal Weight Calculation**:
```
Base weight = 0.5

Modifiers:
+ 0.2  if has aggregates
+ 0.2  if has filters (where clause)
+ 0.1  if has limit
+ 0.2  if has display: detail
```

**Fix**: Add aggregates to boost weight:
```dsl
# Before (weight = 0.5, MONITOR_WALL selected):
workspace dashboard:
  uptime_percentage:
    source: Service
    # Weight: 0.5 (not enough for FOCUS_METRIC)

# After (weight = 0.7, FOCUS_METRIC selected):
workspace dashboard:
  system_uptime:
    source: Service
    aggregate:
      avg_uptime: avg(uptime_percentage)
      total_services: count(Service)
    # Weight: 0.5 + 0.2 = 0.7 ✓ (triggers FOCUS_METRIC)
```

**Reference**: See `docs/ARCHETYPE_SELECTION.md` for complete selection algorithm.

---

### Issue: Expected DUAL_PANE_FLOW but got SCANNER_TABLE

**Symptom**: Workspace shows table view instead of list + detail panes.

**Diagnosis**:
```bash
dazzle layout-plan

# Check for DETAIL_VIEW signal
# Must have: list_weight >= 0.3 AND detail_weight >= 0.3
```

**Cause**: Missing `display: detail` on detail signal.

**DUAL_PANE_FLOW Requirements**:
1. One ITEM_LIST signal with weight >= 0.3
2. One DETAIL_VIEW signal with weight >= 0.3
3. Both signals must be significant (not overshadowed by others)

**Fix**: Add `display: detail` to detail region:
```dsl
# Before (SCANNER_TABLE selected):
workspace contacts:
  contact_list:
    source: Contact
    limit: 20
    # Weight: 0.6 (ITEM_LIST)

  contact_detail:
    source: Contact
    # Weight: 0.5 (TABLE signal, not DETAIL_VIEW)
    # Missing display: detail!

# After (DUAL_PANE_FLOW selected):
workspace contacts:
  contact_list:
    source: Contact
    limit: 20
    # Weight: 0.6 (ITEM_LIST)

  contact_detail:
    source: Contact
    display: detail  # ✓ Creates DETAIL_VIEW signal
    # Weight: 0.7 (DETAIL_VIEW)
```

**Key Learning**: `display: detail` is **essential** for DUAL_PANE_FLOW archetype.

---

### Issue: Expected SCANNER_TABLE but got MONITOR_WALL

**Symptom**: Multiple metrics displayed instead of single table.

**Diagnosis**:
```bash
dazzle layout-plan

# Check:
# - Number of signals (should be 1-2 for SCANNER_TABLE)
# - Table signal weight (must be >= 0.6)
```

**Cause**: Either multiple signals or table weight < 0.6.

**SCANNER_TABLE Requirements**:
- Total table weight >= 0.6
- Typically 1 dominant table signal
- Optional toolbar/filter region (low weight)

**Fix Option 1**: Remove extra signals:
```dsl
# Before (MONITOR_WALL - too many signals):
workspace inventory:
  products_table:
    source: Product
    limit: 100
    # Weight: 0.6

  low_stock_count:
    source: Product
    aggregate:
      count: count(Product WHERE stock < 10)
    # Weight: 0.7 (another significant signal)

# After (SCANNER_TABLE - single dominant signal):
workspace inventory:
  products_table:
    source: Product
    where: active = true
    limit: 100
    # Weight: 0.8 (dominant table signal)
```

**Fix Option 2**: Use engine_hint to force archetype:
```dsl
workspace inventory:
  engine_hint: "scanner_table"  # Force SCANNER_TABLE

  products_table:
    source: Product
    limit: 50

  # Other signals will be suppressed or moved to toolbar
```

---

### Issue: Forcing a specific archetype

**Use Case**: Override automatic selection for UX consistency.

**Solution**: Use `engine_hint` directive:
```dsl
workspace dashboard:
  engine_hint: "monitor_wall"  # Force MONITOR_WALL archetype

  # Your signals...
```

**Valid engine_hint Values**:
- `"focus_metric"`
- `"scanner_table"`
- `"dual_pane_flow"`
- `"monitor_wall"`
- `"command_center"`

**When to Use**:
- UX consistency across workspaces
- Experimentation with different layouts
- Override when algorithm selects wrong pattern
- A/B testing different archetypes

**Warning**: Forcing an archetype may result in suboptimal UX if signals don't match the archetype's intent.

---

## Attention Budget Problems

### Issue: Too many signals, layout feels cluttered

**Symptom**: COMMAND_CENTER archetype selected when you wanted simpler layout.

**Diagnosis**:
```bash
dazzle layout-plan

# Check signal count:
# COMMAND_CENTER: 9+ signals
# MONITOR_WALL: 3-8 signals
# DUAL_PANE_FLOW: 2 signals
# SCANNER_TABLE: 1-2 signals
# FOCUS_METRIC: 1 signal
```

**Cause**: Too many attention signals (9+) triggers COMMAND_CENTER archetype.

**Attention Budget Guidelines**:
- **FOCUS_METRIC**: 1 dominant metric (simple, high impact)
- **SCANNER_TABLE**: 1 table + optional toolbar (data browsing)
- **DUAL_PANE_FLOW**: 2 signals (list + detail)
- **MONITOR_WALL**: 3-8 signals (balanced metrics)
- **COMMAND_CENTER**: 9+ signals (expert interface, high density)

**Fix Option 1**: Reduce signal count:
```dsl
# Before (10 signals → COMMAND_CENTER):
workspace dashboard:
  metric1: ...
  metric2: ...
  metric3: ...
  metric4: ...
  metric5: ...
  metric6: ...
  metric7: ...
  metric8: ...
  metric9: ...
  metric10: ...

# After (4 signals → MONITOR_WALL):
workspace dashboard:
  primary_metric: ...
  urgent_items: ...
  recent_activity: ...
  status_summary: ...
```

**Fix Option 2**: Split into multiple workspaces:
```dsl
# Workspace 1: High-level overview (FOCUS_METRIC)
workspace overview:
  system_health:
    source: Service
    aggregate:
      uptime: avg(uptime_percentage)

# Workspace 2: Detailed metrics (MONITOR_WALL)
workspace details:
  cpu_usage: ...
  memory_usage: ...
  disk_usage: ...
  network_traffic: ...
```

**Key Insight**: Less is often more - prioritize the most important signals.

---

### Issue: Signal not appearing in generated UI

**Symptom**: Defined attention signal doesn't show in layout.

**Diagnosis**:
```bash
dazzle layout-plan

# Check:
# 1. Signal weight (very low weight signals may be filtered)
# 2. Surface capacity (signal may not fit in available surfaces)
# 3. Signal allocation (check which surface signal is assigned to)
```

**Possible Causes**:
1. Signal weight too low (< 0.3)
2. Surface capacity exceeded
3. Higher priority signals took available space

**Fix**: Increase signal weight:
```dsl
# Before (weight = 0.5, may be filtered):
recent_items:
  source: Item

# After (weight = 0.7, more significant):
recent_items:
  source: Item
  where: created_at > now() - interval '24 hours'
  limit: 10
  # Weight: 0.5 + 0.2 (filter) + 0.1 (limit) = 0.8
```

**Debug Command**:
```bash
# See full layout plan with signal allocation
dazzle layout-plan --verbose
```

---

## Module Linking Errors

### Error: "Module not found"

**Symptom**:
```
LinkError: Module 'foo.bar' not found
  Referenced by: baz.qux
```

**Cause**: Module declares dependency on non-existent module.

**Fix**: Ensure module exists and is in DSL path:
```toml
# dazzle.toml
[fileset]
dsl_paths = ["dsl", "shared"]  # Add all module directories
```

```dsl
# foo/bar.dsl - ensure this file exists
module foo.bar

# baz/qux.dsl
module baz.qux
use foo.bar  # ✓ Module must exist
```

---

### Error: "Circular dependency detected"

**Symptom**:
```
LinkError: Circular dependency detected:
  foo.bar → baz.qux → foo.bar
```

**Cause**: Modules have circular `use` dependencies.

**Fix**: Restructure modules to break cycle:
```dsl
# Before (CIRCULAR):
# foo/bar.dsl
module foo.bar
use baz.qux  # ❌ Circular!

# baz/qux.dsl
module baz.qux
use foo.bar  # ❌ Circular!

# After (FIXED):
# common.dsl - shared definitions
module common

# foo/bar.dsl
module foo.bar
use common

# baz/qux.dsl
module baz.qux
use common
```

**Strategy**: Extract shared definitions into common module.

---

### Error: "Unresolved reference"

**Symptom**:
```
LinkError: Unresolved reference to 'User' in module foo.bar
  Entity 'User' not found
```

**Cause**: Module references entity from another module without `use` declaration.

**Fix**: Add `use` declaration:
```dsl
# auth/models.dsl
module auth.models

entity User:
  id: uuid pk
  email: email unique

# foo/bar.dsl - BEFORE (ERROR):
module foo.bar

entity Post:
  author: ref(User)  # ❌ User not in scope!

# foo/bar.dsl - AFTER (FIXED):
module foo.bar
use auth.models  # ✓ Import User

entity Post:
  author: ref(User)  # ✓ User now in scope
```

---

### Error: "Missing root module"

**Symptom**:
```
Error: project.root must be set in dazzle.toml
```

**Cause**: Project manifest missing `root` field.

**Fix**: Add `root` to `dazzle.toml`:
```toml
[project]
name = "my_app"
version = "0.1.0"
root = "my_app.core"  # ✓ Required

[fileset]
dsl_paths = ["dsl"]
```

**Note**: Root module must exist in DSL files:
```dsl
# dsl/app.dsl
module my_app.core  # ✓ Must match root in manifest

app my_app "My Application"
```

---

## Validation Errors

### Error: "Entity must have primary key"

**Symptom**:
```
ValidationError: Entity 'User' must have a primary key field
```

**Cause**: Entity missing `pk` constraint.

**Fix**: Add primary key field:
```dsl
# Before (ERROR):
entity User:
  email: email unique
  name: str

# After (FIXED):
entity User:
  id: uuid pk  # ✓ Primary key required
  email: email unique
  name: str
```

**Primary Key Options**:
- `id: uuid pk` (recommended)
- `id: int pk auto_increment`
- `email: email pk` (natural key)
- `code: str(20) pk`

---

### Error: "Workspace must have at least one attention signal"

**Symptom**:
```
ValidationError: Workspace 'dashboard' has no attention signals
```

**Cause**: Workspace defined but no regions declared.

**Fix**: Add at least one attention signal:
```dsl
# Before (ERROR):
workspace dashboard:
  purpose: "Monitor system"
  # No signals defined!

# After (FIXED):
workspace dashboard:
  purpose: "Monitor system"

  system_health:
    source: Service
    aggregate:
      uptime: avg(uptime_percentage)
```

**Minimum**: Every workspace needs at least 1 attention signal.

---

### Error: "Surface references non-existent entity"

**Symptom**:
```
ValidationError: Surface 'user_form' references entity 'User' which does not exist
```

**Cause**: Surface defined for entity not in scope.

**Fix**: Define entity or import from module:
```dsl
# Fix 1: Define entity
entity User:
  id: uuid pk
  email: email

surface user_form:
  ...

# Fix 2: Import from module
use auth.models  # Contains User entity

surface user_form:
  ...
```

---

## Code Generation Issues

### Issue: Generated Next.js app won't compile

**Symptom**: TypeScript compilation errors in generated code.

**Common Causes**:
1. Missing dependencies in package.json
2. Type mismatches in generated components
3. Invalid React component structure

**Diagnosis**:
```bash
# After generation
cd build/nextjs_semantic/<project_name>
npm install
npm run build  # Check for errors
```

**Fix**: Report issue with:
```bash
# Save error log
npm run build 2>&1 | tee build-error.log

# Include:
# 1. DAZZLE version (dazzle --version)
# 2. DSL files (dsl/*.dsl)
# 3. Build error log
```

---

### Issue: Archetype component not rendering

**Symptom**: Blank page or component not displayed.

**Diagnosis**:
```bash
# Check browser console for errors
# Check generated workspace page

# Verify:
# 1. LayoutPlan has correct archetype
# 2. ArchetypeRouter imports component
# 3. Component props match LayoutPlan structure
```

**Fix**: Check generated `src/app/<workspace>/page.tsx`:
```typescript
// Verify layoutPlan archetype matches intended archetype
const layoutPlan: LayoutPlan = {
  archetype: LayoutArchetype.DUAL_PANE_FLOW,  // ← Check this
  surfaces: [...],
  ...
};
```

If archetype is wrong, check DSL signal definitions (see Archetype Selection Issues).

---

### Issue: Missing accessibility features

**Symptom**: ARIA labels or semantic HTML not in generated code.

**Cause**: Using older DAZZLE version or custom components.

**Fix**: Update to latest version:
```bash
# Homebrew
brew upgrade dazzle

# pipx
pipx upgrade dazzle

# Verify accessibility features
dazzle --version  # Should be >= v0.3.0
```

**Verify** generated components include:
- ARIA labels (`aria-label`, `aria-labelledby`)
- Semantic HTML (`<main>`, `<section>`, `<nav>`)
- Role attributes (`role="region"`)

---

## Debugging Tips

### Enable verbose output

```bash
# See detailed validation messages
dazzle validate --verbose

# See layout planning details
dazzle layout-plan --verbose

# See code generation details
dazzle build --verbose
```

---

### Check intermediate representations

```bash
# Inspect parsed modules
dazzle inspect

# Show patterns detected
dazzle inspect --patterns

# Show type catalog
dazzle inspect --types
```

---

### Test archetype selection

```bash
# See which archetype is selected and why
dazzle layout-plan

# Output shows:
# - Workspace name
# - Signal count and weights
# - Selected archetype
# - Surface allocation
```

---

### Validate DSL incrementally

```bash
# Validate after each change
dazzle validate

# Use strict mode for warnings
dazzle lint --strict

# Check extended validation
dazzle lint
```

---

## Getting Help

### Documentation
- **DSL Reference**: `docs/v0.2/DAZZLE_DSL_REFERENCE.md`
- **Reserved Keywords**: `docs/DSL_RESERVED_KEYWORDS.md`
- **Archetype Selection**: `docs/ARCHETYPE_SELECTION.md`
- **Quick Reference**: `docs/DAZZLE_DSL_QUICK_REFERENCE.md`

### Examples
- `examples/uptime_monitor/` - FOCUS_METRIC
- `examples/inventory_scanner/` - SCANNER_TABLE
- `examples/contact_manager/` - DUAL_PANE_FLOW
- `examples/email_client/` - MONITOR_WALL
- `examples/ops_dashboard/` - COMMAND_CENTER

### Commands
```bash
# Show all available commands
dazzle --help

# Command-specific help
dazzle validate --help
dazzle build --help
dazzle layout-plan --help
```

### Reporting Issues
When reporting issues, include:
1. DAZZLE version (`dazzle --version`)
2. DSL files (`dsl/*.dsl`)
3. Manifest (`dazzle.toml`)
4. Error message (full stack trace)
5. Expected vs actual behavior

---

## Summary

**Most Common Issues**:
1. ❌ Reserved keyword conflicts → Use alternatives from `DSL_RESERVED_KEYWORDS.md`
2. ❌ Wrong archetype selected → Check signal weights and use `engine_hint`
3. ❌ Missing `display: detail` → Required for DUAL_PANE_FLOW
4. ❌ Too many signals → Split into multiple workspaces or reduce count
5. ❌ Module not found → Add to `dsl_paths` and verify `use` declarations

**Quick Fixes**:
- 🔧 `dazzle validate` - Catch errors early
- 🔧 `dazzle layout-plan` - Debug archetype selection
- 🔧 `dazzle lint --strict` - Find warnings
- 🔧 `dazzle inspect --patterns` - Understand structure
- 🔧 Use `engine_hint` - Force specific archetype

**References**:
- Archetype selection algorithm: `docs/ARCHETYPE_SELECTION.md`
- Reserved keywords: `docs/DSL_RESERVED_KEYWORDS.md`
- DSL syntax: `docs/v0.2/DAZZLE_DSL_REFERENCE.md`
- Examples: `examples/` directory

---

**Last Updated**: 2025-11-27
**DAZZLE Version**: 0.3.0
**Applies To**: Semantic UI Layout Engine (Phase 4)
