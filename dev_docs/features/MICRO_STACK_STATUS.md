# Micro Stack - Current Status

## Current State (Interim)

The "micro" stack is currently configured to use the OpenAPI backend as a temporary measure until the full `django_micro` backend is implemented.

### Current Configuration

```python
"micro": StackPreset(
    name="micro",
    description="OpenAPI specification only (simplest option - no code generation yet)",
    backends=["openapi"],
    example_dsl="simple_task",
)
```

### What It Does Now

- ✅ Generates OpenAPI 3.0 specification
- ✅ Perfect for learning DAZZLE DSL syntax
- ✅ Good for API design and documentation
- ❌ Does NOT generate Django code (yet)
- ❌ Does NOT create deployable application (yet)

### User Experience

When running `dazzle demo`:

```bash
$ dazzle demo

No stack specified, using default: 'micro'
(Run 'dazzle demo --list' to see other options)

Creating demo project with stack: micro
Example DSL: simple_task
Location: ./micro-demo

[...]

This is the simplest DAZZLE setup:
  - OpenAPI specification generation
  - No code generation (spec only)
  - Perfect for API design and documentation

📝 Note: Full Django micro backend coming soon!
    For now, use 'api_only' stack for code generation

Perfect for:
  - Learning DAZZLE DSL syntax
  - Designing APIs
  - Generating API documentation
```

## Why This Approach?

### Pros
1. **Works immediately** - No broken backend reference
2. **Useful for learning** - Users can learn DSL and see OpenAPI output
3. **Clear messaging** - Users know it's interim, points to alternatives
4. **Name reserved** - "micro" will mean Django+SQLite when ready
5. **Low friction** - Default command works without errors

### Cons
1. **Not the full vision** - Doesn't deliver on "Django + SQLite" promise yet
2. **Confusing name** - "micro" suggests more than just spec
3. **Same as openapi_only** - Currently redundant with existing stack

## Alternatives Considered

### Option A: No Default (original behavior)
```bash
dazzle demo
# Error: Missing argument 'STACK'
```
❌ Rejected - Too much friction for new users

### Option B: Default to "openapi_only"
```bash
dazzle demo  # Uses openapi_only
```
❌ Rejected - Less clear that there will be a simpler option

### Option C: Default to "api_only" (Django + Docker)
```bash
dazzle demo  # Uses api_only (django_api + docker)
```
❌ Rejected - Requires Docker knowledge, not "micro"

### Option D: Keep "micro" name, use openapi interim (CHOSEN)
```bash
dazzle demo  # Uses micro (openapi for now)
```
✅ Chosen because:
- Works today
- Clear about interim state
- Points to alternatives
- Reserves name for future

## Migration Plan

### Phase 1: Interim (Current)
```python
"micro": StackPreset(
    name="micro",
    description="OpenAPI specification only (simplest option - no code generation yet)",
    backends=["openapi"],
    example_dsl="simple_task",
)
```

**Output**: OpenAPI spec only
**User message**: "Full Django micro backend coming soon!"

### Phase 2: Stub Backend
Create minimal `django_micro` backend that:
- Generates basic Django models
- No admin, views, templates yet
- Shows structure, not production-ready

```python
"micro": StackPreset(
    name="micro",
    description="Basic Django models (early preview)",
    backends=["django_micro"],  # Stub implementation
    example_dsl="simple_task",
)
```

### Phase 3: Full Implementation
Complete `django_micro` backend with:
- Django models, admin, views, templates
- SQLite configuration
- Deployment configs (Heroku, Vercel, etc.)

```python
"micro": StackPreset(
    name="micro",
    description="Single Django app with SQLite (easiest to deploy on Heroku/Vercel)",
    backends=["django_micro"],  # Full implementation
    example_dsl="simple_task",
)
```

**Output**: Complete, deployable Django app
**User message**: No interim warning, just usage instructions

## Implementation Checklist

### ✅ Completed
- [x] Define micro stack preset
- [x] Set as default for demo command
- [x] Configure with openapi backend (interim)
- [x] Add clear messaging about interim state
- [x] Point users to api_only for code generation
- [x] Update documentation

### 🚧 In Progress
- [ ] Design django_micro backend architecture
- [ ] Implement model generation
- [ ] Add admin configuration
- [ ] Create views and templates
- [ ] Generate forms from surfaces
- [ ] Add deployment configurations

### 📋 Planned
- [ ] Full Django micro backend
- [ ] Testing and validation
- [ ] Deployment guides
- [ ] Update messaging (remove "coming soon")
- [ ] Tutorial updates

## User Communication

### Current Messaging

**Demo output**:
```
📝 Note: Full Django micro backend coming soon!
    For now, use 'api_only' stack for code generation
```

**--list output**:
```
  micro (default)
    OpenAPI specification only (simplest option - no code generation yet)
    Backends: openapi
    Example: simple_task
```

### When django_micro is Ready

**Demo output**:
```
This is the simplest DAZZLE setup:
  - Single Django application
  - SQLite database (no separate DB server needed)
  - Easy to deploy on Heroku, Vercel, or PythonAnywhere
```

**--list output**:
```
  micro (default)
    Single Django app with SQLite (easiest to deploy on Heroku/Vercel)
    Backends: django_micro
    Example: simple_task
```

## Testing Current State

### Verify it works:
```bash
# Should not error
dazzle demo

# Should create project with OpenAPI backend
cd micro-demo
dazzle build

# Should generate OpenAPI spec
ls build/openapi/openapi.yaml

# Should show helpful message
# "📝 Note: Full Django micro backend coming soon!"
```

### Verify messaging:
```bash
# Should show interim status
dazzle demo --list

# Should indicate openapi backend
# Should show "Example: simple_task"
```

## Impact Assessment

### Short-term (Interim State)
- ✅ Users can try DAZZLE immediately
- ✅ Learn DSL syntax
- ✅ See OpenAPI output
- ⚠️ May expect more (Django code)
- ⚠️ Need to point to api_only for code

### Long-term (After Implementation)
- ✅ True "simplest setup" achieved
- ✅ Django + SQLite out of the box
- ✅ Easy deployment story
- ✅ Matches original vision
- ✅ Better onboarding

## Related Documents

- [MICRO_STACK_SPEC.md](MICRO_STACK_SPEC.md) - Full specification for django_micro backend
- [MICRO_STACK_IMPLEMENTATION.md](MICRO_STACK_IMPLEMENTATION.md) - Initial configuration
- [DEMO_COMMAND_IMPROVEMENTS.md](DEMO_COMMAND_IMPROVEMENTS.md) - Example transparency updates

---

**Status**: Interim (OpenAPI only)
**Next**: Implement django_micro backend
**Priority**: High - Core feature for new user experience
**ETA**: TBD based on backend development priorities
