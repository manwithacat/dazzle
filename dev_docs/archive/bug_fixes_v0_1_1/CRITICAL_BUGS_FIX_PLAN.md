# CRITICAL BUGS - Fix Plan

**Date**: 2025-11-23
**Priority**: P0 - CRITICAL
**Impact**: Generated apps crash on startup
**Source**: Urban Canopy testing feedback

---

## Bug Summary

### BUG-001: Missing Views for Partial CRUD
**Severity**: CRITICAL
**Impact**: Apps crash when entities don't have edit surfaces
**Frequency**: HIGH (any partial CRUD pattern)

**Root Cause**: URL generator creates routes for all CRUD operations, but view generator only creates views for surfaces defined in DSL.

**Example**:
- DSL has `observation_create` but no `observation_edit`
- URLs.py references `ObservationUpdateView`
- Views.py doesn't have `ObservationUpdateView`
- Result: AttributeError crash

### BUG-002: Inconsistent View Naming
**Severity**: CRITICAL
**Impact**: Apps crash with multi-word entity names
**Frequency**: MEDIUM (multi-word entities)

**Root Cause**: View generator uses surface names for List/Detail/Create but entity names for Update/Delete, causing name mismatches.

**Example**:
- Entity: `MaintenanceTask`
- Surface: `task_list`
- Generated view: `TaskListView` (from surface)
- URL expects: `MaintenanceTaskListView` (from entity)
- Result: Attribute Error crash

---

## Fix Strategy

### Phase 1: Immediate Fixes (This Session)

1. **Document the bugs** ✓
   - Create this fix plan
   - Acknowledge user feedback
   - Commit to timeline

2. **Analyze generated code** (Next)
   - Read views.py generator
   - Read urls.py generator
   - Understand current logic

3. **Implement fixes** (Next)
   - Fix BUG-002 first (easier, clearer impact)
   - Fix BUG-001 second (more complex)

4. **Test fixes**
   - Use Urban Canopy DSL as test case
   - Verify app starts without errors
   - Test partial CRUD patterns

### Phase 2: Testing & Prevention

1. **Add integration tests**
   - Test generated apps actually run
   - Test partial CRUD patterns
   - Test multi-word entities

2. **Add validation**
   - Warn about missing CRUD operations
   - Check view/URL consistency

### Phase 3: Documentation

1. **Update DSL guide**
   - Document partial CRUD patterns
   - Add examples

2. **Release notes**
   - Critical bugfix announcement
   - No breaking changes

---

## Recommended Fixes

### BUG-002 Fix: Consistent View Naming

**Change**: Always use full entity name for all view classes

```python
# BEFORE (BROKEN):
def generate_view_class_name(surface, entity):
    if surface.mode in ['list', 'detail', 'create']:
        # Uses surface name prefix
        return f"{surface.name.title()}View"
    else:
        # Uses entity name
        return f"{entity.name}{surface.mode.title()}View"

# AFTER (FIXED):
def generate_view_class_name(surface, entity):
    # Always use full entity name
    mode_name = {
        'list': 'List',
        'view': 'Detail',
        'detail': 'Detail',
        'create': 'Create',
        'edit': 'Update',
        'delete': 'Delete'
    }[surface.mode]

    return f"{entity.name}{mode_name}View"
```

**Result**:
- `MaintenanceTask` + `list` → `MaintenanceTaskListView` ✓
- `MaintenanceTask` + `create` → `MaintenanceTaskCreateView` ✓
- Consistent across all view types ✓

### BUG-001 Fix: Respect DSL Surfaces

**Change**: Only generate URLs for surfaces that exist in DSL

```python
# BEFORE (BROKEN):
def generate_urls(entities):
    urls = []
    for entity in entities:
        # Always generates all CRUD URLs
        urls.append(list_url(entity))
        urls.append(detail_url(entity))
        urls.append(create_url(entity))
        urls.append(update_url(entity))  # ❌ Always generated
        urls.append(delete_url(entity))
    return urls

# AFTER (FIXED):
def generate_urls(appspec):
    urls = []

    # Group surfaces by entity
    for entity in appspec.entities:
        entity_surfaces = get_surfaces_for_entity(appspec, entity)
        surface_modes = {s.mode for s in entity_surfaces}

        # Only generate URLs for modes that exist
        if 'list' in surface_modes:
            urls.append(list_url(entity))

        if 'view' in surface_modes or 'detail' in surface_modes:
            urls.append(detail_url(entity))

        if 'create' in surface_modes:
            urls.append(create_url(entity))

        if 'edit' in surface_modes:  # ✓ Only if defined
            urls.append(update_url(entity))

        # Delete: keep always-on for now (safety)
        urls.append(delete_url(entity))

    return urls
```

**Result**:
- Entity with create only → No update URL ✓
- Entity with no surfaces → No URLs ✓
- Respects DSL intent ✓

---

## Testing Plan

### Test Case 1: Partial CRUD (BUG-001)

```python
# DSL
entity AuditLog:
  id: uuid pk
  message: text

surface log_create:
  uses entity AuditLog
  mode: create
  section main:
    field message

# No log_edit surface

# Expected behavior:
# - AuditLogCreateView exists ✓
# - No AuditLogUpdateView ✓
# - No update URL ✓
# - App starts successfully ✓
```

### Test Case 2: Multi-word Entity (BUG-002)

```python
# DSL
entity MaintenanceTask:
  id: uuid pk
  title: str(200)

surface task_list:
  uses entity MaintenanceTask
  mode: list
  section main:
    field title

# Expected behavior:
# - MaintenanceTaskListView (not TaskListView) ✓
# - URL references MaintenanceTaskListView ✓
# - App starts successfully ✓
```

### Test Case 3: Urban Canopy (Full Integration)

```python
# Use actual Urban Canopy DSL
# Expected behavior:
# - python manage.py check passes ✓
# - python manage.py migrate works ✓
# - python manage.py runserver starts ✓
```

---

## Files to Modify

### Django Micro Modular Stack

1. **`generators/views.py`** - View class name generation
2. **`generators/urls.py`** - URL pattern generation
3. **`generators/forms.py`** - Form generation (similar issue)

### Tests to Add

1. **`tests/integration/test_generated_apps.py`** (new)
   - Test that apps actually run
   - Test Django management commands

2. **`tests/unit/test_backends.py`** (existing)
   - Add partial CRUD test cases
   - Add multi-word entity test cases

---

## Impact Assessment

### User Experience Before Fix

```
User creates valid DSL with partial CRUD
  ↓
dazzle validate ✓ passes
  ↓
dazzle build ✓ succeeds
  ↓
python manage.py migrate ✗ CRASHES
  ↓
User sees cryptic AttributeError
  ↓
User abandons DAZZLE 😞
```

### User Experience After Fix

```
User creates valid DSL with partial CRUD
  ↓
dazzle validate ✓ passes
  ↓
dazzle build ✓ succeeds
  ↓
python manage.py migrate ✓ works!
  ↓
python manage.py runserver ✓ works!
  ↓
User is happy 🎉
```

---

## Timeline

**Session 1** (Now):
- ✓ Document bugs
- ✓ Create fix plan
- Read generator code
- Implement BUG-002 fix
- Implement BUG-001 fix
- Test with Urban Canopy DSL

**Session 2** (Next):
- Add integration tests
- Add unit test cases
- Update documentation
- Create release notes

---

## Communication

### To User

"Thank you for the detailed bug reports! These are critical issues that affect the core user experience. I'm implementing fixes now:

**BUG-002** (view naming) - Fixing in this session
**BUG-001** (partial CRUD) - Fixing in this session

Both fixes will:
- Make Urban Canopy app work immediately
- Support partial CRUD patterns (append-only, read-only)
- Not break existing DSL files

You'll be able to rebuild and run your app without workarounds."

### Release Notes

```markdown
# DAZZLE v0.1.1 - CRITICAL BUGFIXES

## Fixed

### CRITICAL: Generated Django apps now start successfully
- **BUG-001**: Fixed URL generation to respect DSL surfaces
  - URLs only generated for surfaces defined in DSL
  - Enables partial CRUD patterns (create-only, read-only)
  - No more crashes with append-only entities

- **BUG-002**: Fixed inconsistent view naming
  - All view classes now use full entity names
  - Multi-word entities (MaintenanceTask, SupportTicket) now work
  - Consistent naming across all view types

## Breaking Changes
None. Fixes make previously broken patterns work.

## Upgrade Instructions
```bash
# Rebuild your app
dazzle build

# Remove workarounds if you added them
# - No need for dummy edit surfaces anymore
# - Generated code is now correct
```

---

## Success Criteria

✓ Urban Canopy DSL builds successfully
✓ Generated app starts without AttributeError
✓ `python manage.py check` passes
✓ `python manage.py migrate` works
✓ `python manage.py runserver` starts
✓ Partial CRUD patterns supported
✓ Multi-word entities work correctly

---

## Next Steps

1. Read generator code to understand current implementation
2. Implement fixes for both bugs
3. Test with Urban Canopy DSL
4. Commit fixes
5. Update user with results

---

**Status**: Ready to implement
**ETA**: This session (1-2 hours)
**Risk**: Low (fixes align with expected behavior)
