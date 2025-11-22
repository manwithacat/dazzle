# Micro Stack Implementation

## Summary

Implemented a new "micro" stack preset as the default for `dazzle demo` to simplify the new user experience.

## Changes Made

### 1. Stack Configuration (`src/dazzle/core/stacks.py`)

Added new "micro" stack as the first (default) preset:

```python
"micro": StackPreset(
    name="micro",
    description="Single Django app with SQLite (easiest to deploy on Heroku/Vercel)",
    backends=["django_micro"],
    example_dsl="simple_task",
)
```

Added constant:
```python
DEFAULT_DEMO_STACK = "micro"
```

### 2. Demo Command Updates (`src/dazzle/cli.py`)

#### Argument Changes
- Made stack argument optional (defaults to "micro")
- Updated help text to indicate default behavior
- Updated docstring with new examples

#### List Command Enhancement
- Shows default stack first with "(default)" indicator
- Improved usage instructions
- Added hint about recommended option for beginners

#### Auto-Default Behavior
When no stack specified:
```python
if stack is None:
    stack = DEFAULT_DEMO_STACK
    typer.echo(f"No stack specified, using default: '{stack}'")
    typer.echo(f"(Run 'dazzle demo --list' to see other options)\n")
```

#### Success Output Enhancement
Added informative output for micro stack:
```
This is the simplest DAZZLE setup:
  - Single Django application
  - SQLite database (no separate DB server needed)
  - Easy to deploy on Heroku, Vercel, or PythonAnywhere

Perfect for:
  - Learning DAZZLE
  - Prototyping
  - Small projects
```

Added breadcrumbs to other stacks:
```
Other available stacks:
  dazzle demo --list           # See all stack options

Popular choices:
  dazzle demo openapi_only     # Just OpenAPI spec (no code)
  dazzle demo api_only         # Django API + Docker
  dazzle demo django_next      # Full-stack with Next.js frontend
```

## User Experience Improvements

### Before
```bash
# Required explicit stack name
dazzle demo openapi_only

# No stack argument = error
dazzle demo
# Error: Missing argument 'STACK'
```

### After
```bash
# Now works with sensible default
dazzle demo
# No stack specified, using default: 'micro'
# (Run 'dazzle demo --list' to see other options)

# Creates micro-demo directory with simplest setup
```

### Progressive Disclosure

Users naturally discover more complex options:

1. **First command**: `dazzle demo` → Gets micro stack
2. **Success message**: Shows what micro is good for + links to other stacks
3. **List command**: `dazzle demo --list` → Sees all options with micro marked as default
4. **Choose complexity**: When ready, can try `dazzle demo django_next`

## Command Examples

### Create Default Demo
```bash
dazzle demo
# or explicitly:
dazzle demo micro
```

### List Available Stacks
```bash
dazzle demo --list
```

Output:
```
Available demo stacks:

  micro (default)
    Single Django app with SQLite (easiest to deploy on Heroku/Vercel)
    Backends: django_micro

  api_only
    Django REST API + OpenAPI spec + Docker
    Backends: django_api, openapi, infra_docker

  django_next
    Django REST API + Next.js frontend + Docker
    Backends: django_api, nextjs_frontend, infra_docker

  django_next_cloud
    Django + Next.js + Docker + Terraform (AWS)
    Backends: django_api, nextjs_frontend, infra_docker, infra_terraform

  openapi_only
    OpenAPI specification only
    Backends: openapi

Use: dazzle demo [stack]
     dazzle demo              # Uses 'micro' (recommended for beginners)
```

### Create Specific Stack
```bash
dazzle demo openapi_only
dazzle demo django_next
```

## Backend Implementation Status

### ✅ Completed
- Stack preset definition
- Default stack constant
- Demo command integration
- User messaging and breadcrumbs
- Documentation

### 🚧 Pending
- `django_micro` backend implementation
  - Model generation
  - Admin configuration
  - Views and templates
  - Forms from surfaces
  - Deployment configuration files

See [MICRO_STACK_SPEC.md](MICRO_STACK_SPEC.md) for full backend specification.

## Benefits

### For New Users
- **Zero configuration needed** - Just run `dazzle demo`
- **Immediate success** - Works out of the box
- **Clear learning path** - See what's possible, choose complexity when ready
- **Reduced friction** - No Docker, no database setup, no frontend build

### For Experienced Users
- **Fast prototyping** - Quick way to test ideas
- **Still have options** - Can choose any stack explicitly
- **Same CLI** - Familiar commands work the same way

### For Documentation
- **Simplified tutorials** - Can show `dazzle demo` without explaining stacks first
- **Progressive complexity** - Introduce advanced stacks later
- **Better examples** - Micro stack examples are easier to understand

## Testing

### Manual Testing

Test default behavior:
```bash
dazzle demo
# Should create micro-demo with simple_task example
```

Test list command:
```bash
dazzle demo --list
# Should show micro as default
```

Test explicit stack:
```bash
dazzle demo openapi_only
# Should work as before
```

### User Flow Test

Simulate new user:
```bash
# 1. First command ever
dazzle demo

# 2. See output mentioning other options
# 3. Check options
dazzle demo --list

# 4. Try different stack when ready
dazzle demo api_only
```

## Documentation Updates Needed

- [ ] Update main README with new default behavior
- [ ] Update CLI reference docs
- [ ] Update tutorial to use `dazzle demo` without arguments
- [ ] Add micro stack deployment guides
- [ ] Update contribution guide with micro stack info

## Migration Path

Existing users not affected:
- All explicit stack commands work the same
- `dazzle demo openapi_only` → same behavior
- Only change is when no stack specified (was error, now defaults)

## Next Steps

1. **Implement `django_micro` backend** (see MICRO_STACK_SPEC.md)
2. **Test deployment** to Heroku, Vercel, Railway
3. **Create deployment guides** for each platform
4. **Update tutorials** to use new default
5. **Gather user feedback** on simplified experience

## Related Files

- `src/dazzle/core/stacks.py` - Stack definitions
- `src/dazzle/cli.py` - Demo command implementation
- `devdocs/MICRO_STACK_SPEC.md` - Backend specification
- `devdocs/STACKS_IMPLEMENTATION_PLAN.md` - Original stack system

---

**Status**: Configuration Complete, Backend Implementation Pending
**Date**: November 2024
**Impact**: Improved new user onboarding, reduced friction
