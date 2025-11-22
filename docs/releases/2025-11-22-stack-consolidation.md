# Stack Terminology Consolidation

**Date**: November 22, 2025
**Version**: Post-v0.1.0

## Summary

Consolidated all user-facing terminology from "backend" and "infra" to unified "stack" concept.

## Changes Made

### 1. Directory Restructure
- **Renamed**: `src/dazzle/backends/` → `src/dazzle/stacks/`
- **Renamed**: `infra_docker.py` → `docker.py`
- **Renamed**: `infra_terraform.py` → `terraform.py`
- **Class names**: `DockerBackend` → `DockerStack`, `TerraformBackend` → `TerraformStack`

### 2. CLI Commands
- **Renamed**: `dazzle backends` → `dazzle stacks`
- **Deprecated**: `dazzle infra` (shows migration guide to `dazzle build --stack`)
- **Updated**: `dazzle build` now uses `--stack` (deprecates `--backend` and `--backends`)

### 3. Stack Presets
Updated all presets to use new stack names:
- `django_next`: `["django_api", "nextjs_frontend", "docker"]`
- `django_next_cloud`: `["django_api", "nextjs_frontend", "docker", "terraform"]`
- `api_only`: `["django_api", "openapi", "docker"]`

### 4. Import Updates
All imports changed from:
- `from dazzle.backends import ...` → `from dazzle.stacks import ...`
- Updated in: `cli.py`, `core/stacks.py`, `stacks/__init__.py`

### 5. Documentation
**Updated files:**
- `README.md` - All "backend" → "stack"
- `.claude/CLAUDE.md` - Updated architecture description
- `src/dazzle/cli.py` - Help text, examples, error messages
- `src/dazzle/core/llm_context.py` - Generated context files

**Path references**:
- `build/infra_docker` → `build/docker`
- `build/infra_terraform` → `build/terraform`

## Rationale

### Problem
Users faced terminology confusion:
1. **Three concepts**: "backend", "infra", "stack"
2. **Overlapping**: Infrastructure implementations (`infra_docker`) were backends included in stacks
3. **Inconsistent UX**: `--backend` vs `--stack` vs `dazzle infra`

### Solution
**Single concept: "Stack"**
- A stack is what you build (single or multiple technologies)
- Can be a preset name (`micro`, `django_next`) or custom list (`docker,terraform`)
- Infrastructure is just a type of stack (not a separate concept)

### User Experience

**Before:**
```bash
dazzle backends                    # List implementations
dazzle build --backend openapi      # Build single
dazzle build --backends django,next # Build multiple
dazzle infra docker                 # Special command for infra
```

**After:**
```bash
dazzle stacks                       # List all stacks
dazzle build --stack openapi        # Build single
dazzle build --stack django,next    # Build multiple
dazzle build --stack docker         # No special treatment
```

## Implementation Details

### Backend Class (Internal)
The `Backend` base class name **remains unchanged** as an implementation detail:
- User-facing: "stack"
- Code-facing: `Backend` class, `BackendCapabilities`, `BackendError`
- Developers extending DAZZLE work with `Backend` API

### Stack Resolution
`resolve_stack_backends()` now handles:
1. Preset names: `"micro"` → `["django_micro_modular"]`
2. Comma-separated lists: `"docker,terraform"` → `["docker", "terraform"]`
3. Single implementations: `"openapi"` → `["openapi"]`

### Deprecation Strategy
**Deprecated (show warnings):**
- `dazzle backends` → redirects to `dazzle stacks`
- `--backend` and `--backends` flags → show migration message
- `dazzle infra` → shows migration guide

**Removal planned**: v0.2.0

## Migration Guide

### For Users

**Command changes:**
| Old | New |
|-----|-----|
| `dazzle backends` | `dazzle stacks` |
| `dazzle build --backend openapi` | `dazzle build --stack openapi` |
| `dazzle build --backends django,next` | `dazzle build --stack django,next` |
| `dazzle infra docker` | `dazzle build --stack docker` |
| `dazzle infra --list` | `dazzle stacks` |

**Stack names:**
| Old | New |
|-----|-----|
| `infra_docker` | `docker` |
| `infra_terraform` | `terraform` |

### For Developers

**Import changes:**
```python
# Old
from dazzle.backends import Backend, get_backend, list_backends

# New
from dazzle.stacks import Backend, get_backend, list_backends
```

**Directory structure:**
```
src/dazzle/
├── stacks/          # Renamed from backends/
│   ├── __init__.py
│   ├── django_micro_modular/
│   ├── openapi.py
│   ├── docker.py        # Renamed from infra_docker.py
│   └── terraform.py     # Renamed from infra_terraform.py
```

## Benefits

1. **Simplified mental model**: One concept instead of three
2. **Consistent CLI**: All building done through `dazzle build --stack`
3. **Clearer purpose**: Stacks generate application artifacts (app code, APIs, deployment configs)
4. **Easier documentation**: "Stack" is intuitive for users

## Files Modified

**Core:**
- `src/dazzle/stacks/` (renamed directory)
- `src/dazzle/stacks/docker.py` (renamed class)
- `src/dazzle/stacks/terraform.py` (renamed class)
- `src/dazzle/cli.py` (updated commands, help text)
- `src/dazzle/core/stacks.py` (updated presets, resolution logic)
- `src/dazzle/core/llm_context.py` (updated paths)

**Documentation:**
- `README.md`
- `.claude/CLAUDE.md`

**Total files changed**: ~8 files
**Lines changed**: ~200 lines

## Testing

**Manual verification needed:**
1. `dazzle stacks` - lists all available stacks
2. `dazzle build --stack micro` - builds micro stack
3. `dazzle build --stack docker,terraform` - builds multiple
4. `dazzle backends` - shows deprecation warning
5. `dazzle infra docker` - shows migration guide
6. `dazzle build --backend openapi` - shows deprecation warning

## Status

✅ **Complete** - All refactoring done, backward compatibility maintained through deprecation warnings.
