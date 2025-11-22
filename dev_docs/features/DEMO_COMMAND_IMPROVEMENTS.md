# Demo Command Improvements - Example Transparency

## Summary

Enhanced the `dazzle demo` command to explicitly show which example is being built and provide clear guidance on accessing other included examples.

## Changes Made

### 1. Explicit Example Reporting

**Before**:
```
Creating demo project: micro
Location: ./micro-demo
```

**After**:
```
Creating demo project with stack: micro
Example DSL: simple_task
Location: ./micro-demo
```

Now users immediately see:
- Which stack they're using
- Which example DSL is being built
- Where the project is being created

### 2. Enhanced --list Output

Shows which example each stack uses:

```bash
$ dazzle demo --list

Available demo stacks:

  micro (default)
    Single Django app with SQLite (easiest to deploy on Heroku/Vercel)
    Backends: django_micro
    Example: simple_task

  api_only
    Django REST API + OpenAPI spec + Docker
    Backends: django_api, openapi, infra_docker
    Example: simple_task

  django_next
    Django REST API + Next.js frontend + Docker
    Backends: django_api, nextjs_frontend, infra_docker
    Example: support_tickets
    
  [...]

Use: dazzle demo [stack]
     dazzle demo              # Uses 'micro' (recommended for beginners)
```

### 3. Examples Discovery Section

Added comprehensive guidance at the end of successful demo creation:

```
------------------------------------------------------------
Explore other examples:
  DAZZLE includes example projects in your installation:

  • simple_task       - Basic CRUD app (1 entity, 4 surfaces)
  • support_tickets   - Multi-entity system (3 entities, relationships)

  To use an example:
    dazzle clone simple_task          # Copy to current directory
    dazzle clone support_tickets      # Copy support_tickets example

  Or browse examples:
    # Find examples directory
    python -c 'import dazzle; print(dazzle.__file__.replace("__init__.py", "../examples"))'
============================================================
```

## Complete User Flow Example

### Running `dazzle demo`

```bash
$ dazzle demo

No stack specified, using default: 'micro'
(Run 'dazzle demo --list' to see other options)

Creating demo project with stack: micro
Example DSL: simple_task
Location: /Users/me/micro-demo

✓ Demo project created: /Users/me/micro-demo
✓ Initialized git repository
✓ Created LLM context files (LLM_CONTEXT.md, .llm/, .claude/, .copilot/)

Verifying project setup...
✓ Verification passed

Building project...
✓ Build complete

============================================================
Next steps:
  cd ./micro-demo

This is the simplest DAZZLE setup:
  - Single Django application
  - SQLite database (no separate DB server needed)
  - Easy to deploy on Heroku, Vercel, or PythonAnywhere

Perfect for:
  - Learning DAZZLE
  - Prototyping
  - Small projects

------------------------------------------------------------
Other available stacks:
  dazzle demo --list           # See all stack options

Popular choices:
  dazzle demo openapi_only     # Just OpenAPI spec (no code)
  dazzle demo api_only         # Django API + Docker
  dazzle demo django_next      # Full-stack with Next.js frontend

------------------------------------------------------------
Explore other examples:
  DAZZLE includes example projects in your installation:

  • simple_task       - Basic CRUD app (1 entity, 4 surfaces)
  • support_tickets   - Multi-entity system (3 entities, relationships)

  To use an example:
    dazzle clone simple_task          # Copy to current directory
    dazzle clone support_tickets      # Copy support_tickets example

  Or browse examples:
    # Find examples directory
    python -c 'import dazzle; print(dazzle.__file__.replace("__init__.py", "../examples"))'
============================================================
```

## User Benefits

### 1. Transparency
- **See what's happening**: Users know exactly which example is being used
- **No surprises**: Clear about what they're getting
- **Reproducible**: Can recreate same setup by specifying example

### 2. Discovery
- **Learn about examples**: See all available examples upfront
- **Easy access**: Direct commands to try other examples
- **Natural progression**: From simple_task to support_tickets

### 3. Guidance
- **Multiple paths**: Demo vs clone commands explained
- **Clear differences**: Understand when to use each
- **Self-service**: Can explore without asking for help

## Example Characteristics

### simple_task
- **Entities**: 1 (Task)
- **Surfaces**: 4 (list, view, create, edit)
- **Complexity**: Low
- **Best for**: Learning basics, first project
- **Features**: Basic CRUD, field types, auto-timestamps

### support_tickets
- **Entities**: 3 (User, Ticket, Comment)
- **Surfaces**: 4 (list, detail, create, edit for Ticket)
- **Complexity**: Medium
- **Best for**: Understanding relationships, real-world patterns
- **Features**: Foreign keys, enums, optional/required relationships

## Commands for Working with Examples

### Using Demo (Quick Start)
```bash
# Create new project with stack + example
dazzle demo                    # Default: micro + simple_task
dazzle demo django_next        # Next.js + support_tickets
dazzle demo openapi_only       # Just spec + simple_task
```

### Using Clone (Explore Examples)
```bash
# List available examples
dazzle clone --list

# Clone an example
dazzle clone simple_task       # Prompts for stack choice
dazzle clone simple_task --stack micro
dazzle clone support_tickets --stack django_next

# Clone to custom location
dazzle clone simple_task --path ./my-project
```

### Manual Exploration
```bash
# Find examples directory
python -c 'import dazzle; import os; print(os.path.dirname(dazzle.__file__) + "/../examples")'

# Or locate package
pip show dazzle | grep Location

# Browse examples
cd $(pip show dazzle | grep Location | cut -d' ' -f2)/../examples
ls -la
```

## Educational Flow

### Beginner Path
1. **Start**: `dazzle demo` → Gets micro + simple_task
2. **Learn**: Explore generated code, understand basics
3. **Experiment**: Modify simple_task DSL, rebuild
4. **Next**: `dazzle clone support_tickets` → See relationships
5. **Advanced**: `dazzle demo django_next` → Full stack

### Quick Prototyper Path
1. **Start**: `dazzle demo` → Fast setup
2. **Customize**: Edit DSL for their use case
3. **Deploy**: Push to Heroku/Vercel
4. **Scale**: When ready, try other stacks

### Explorer Path
1. **List**: `dazzle demo --list` → See all options
2. **Clone**: `dazzle clone simple_task` → Start simple
3. **Compare**: `dazzle clone support_tickets` → See complexity
4. **Choose**: Pick stack that matches needs

## Future Enhancements

### More Examples
- [ ] **blog** - Posts, comments, categories, tags
- [ ] **ecommerce** - Products, orders, customers, payments
- [ ] **crm** - Contacts, companies, deals, activities
- [ ] **inventory** - Items, warehouses, stock movements
- [ ] **project_manager** - Projects, tasks, milestones, teams

### Interactive Selection
```bash
dazzle demo --interactive

# Shows:
Choose a stack:
  1. micro (recommended for beginners)
  2. openapi_only
  3. api_only
  4. django_next

Choose an example:
  1. simple_task (basic CRUD)
  2. support_tickets (relationships)
```

### Example Templates
```bash
# Use example as template for new project
dazzle new my-project --template simple_task
dazzle new my-crm --template support_tickets

# Customizes names, keeps structure
```

## Documentation Updates

Updated files:
- `src/dazzle/cli.py` - Demo command implementation
- `devdocs/DEMO_COMMAND_IMPROVEMENTS.md` - This document
- `devdocs/MICRO_STACK_IMPLEMENTATION.md` - Stack details

Should update:
- [ ] Main README - Show new demo output
- [ ] Quick Start guide - Use new demo command
- [ ] Tutorial - Reference example transparency
- [ ] CLI Reference - Document new output format

## Testing

### Manual Tests

Test example reporting:
```bash
dazzle demo
# Should show "Example DSL: simple_task"

dazzle demo django_next
# Should show "Example DSL: support_tickets"
```

Test list output:
```bash
dazzle demo --list
# Should show example for each stack
```

Test examples guidance:
```bash
dazzle demo
# Success output should include examples section
```

### Verify Examples Work

```bash
# Clone and validate each example
dazzle clone simple_task --path /tmp/test-simple
cd /tmp/test-simple
dazzle validate

dazzle clone support_tickets --path /tmp/test-tickets
cd /tmp/test-tickets
dazzle validate
```

## Impact

### Metrics to Track
- Time to first successful project
- Support questions about examples
- Example usage distribution
- Progression from simple to complex examples

### Expected Improvements
- ✅ Clearer onboarding experience
- ✅ Better example discovery
- ✅ Reduced "what example is this?" questions
- ✅ Natural learning progression
- ✅ More users exploring multiple examples

---

**Status**: Complete
**Date**: November 2024
**Impact**: Improved transparency and discoverability
