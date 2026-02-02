"""
LLM context generation for DAZZLE projects.

Generates context files that help LLMs understand DAZZLE-generated projects.
"""

from pathlib import Path


def generate_llm_context_md(project_name: str, stack_name: str | None = None) -> str:
    """Generate root LLM_CONTEXT.md content."""
    stack_info = f"\nThis project uses the `{stack_name}` stack." if stack_name else ""

    return f"""# LLM Context: {project_name}

This project is generated and maintained by **DAZZLE** — a DSL-first application generator.

## What is DAZZLE?

DAZZLE transforms high-level domain specifications into complete, production-ready applications.
It works by parsing a declarative DSL, building an intermediate representation (IR), and using
pluggable backends to generate code, configurations, and infrastructure.
{stack_info}

## Source of Truth

**All application logic is defined in DSL files, not in generated code.**

The single source of truth for this project:
- `dsl/*.dsl` — Domain entities, surfaces, experiences, services
- `dazzle.toml` — Project manifest, stack configuration, build settings

## Workflow

### 1. Validate the DSL
```bash
dazzle validate
```

### 2. Generate artifacts
```bash
dazzle build
```

This regenerates all code from the DSL. Generated artifacts live in `build/`.

### 3. Run the application
```bash
# If using Docker stack:
cd build/docker
docker compose up

# If using Django directly:
cd build/django_api
python manage.py runserver
```

### 4. Test
```bash
pytest  # (if tests are generated or added)
```

## Rules for Modifying Behavior

### ✅ DO:
- **Edit DSL files** (`dsl/*.dsl`) to change entities, fields, relationships, surfaces
- **Edit `dazzle.toml`** to change stack configuration, backend selection
- **Run `dazzle build`** after DSL changes to regenerate code
- **Add custom business logic** in designated extension points (if provided)
- **Modify infrastructure configs** in `build/infra_*` if needed

### ❌ DON'T:
- **Hand-edit generated code** in `build/` unless explicitly marked as safe
- **Embed infrastructure configuration** into DSL (use `dazzle.toml` instead)
- **Duplicate entity definitions** across DSL and generated code
- **Ignore validation errors** — fix DSL first, then rebuild

## Architecture

```
{project_name}/
├── dsl/                    # DSL source files (EDIT THESE)
├── dazzle.toml            # Project manifest (EDIT THIS)
├── build/                 # Generated artifacts (REGENERATE, DON'T EDIT)
│   ├── django_api/        # Backend API (if using Django)
│   ├── frontend/          # Frontend app (if using Next.js)
│   └── infra_*/           # Infrastructure configs
├── LLM_CONTEXT.md         # This file
├── .llm/                  # Extended LLM documentation
└── .claude/               # Claude Code configuration
```

## Getting Help

1. **Read `.llm/DAZZLE_PRIMER.md`** for deeper DAZZLE concepts
2. **Check `.claude/PROJECT_CONTEXT.md`** for project-specific guidance
3. **Inspect `dsl/*.dsl`** to understand current domain model
4. **Run `dazzle --help`** to see available commands

## Troubleshooting

### Build Failures

**Error: "Backend 'xyz' not found"**
- Your stack requires a backend that isn't available
- **Solution**: Use explicit backends: `dazzle build --backends django_api,openapi`
- Or change the stack in `dazzle.toml` to a compatible one

**Validation Errors**
- DSL syntax errors prevent building
- **Solution**: Run `dazzle validate` to see specific errors
- Fix the reported issues in your DSL files

**Generated Code Conflicts**
- Manual edits to `build/` will be overwritten
- **Solution**: Make changes in DSL, then rebuild

### Common Questions

**Q: Can I edit generated code?**
A: Generally no. Always edit DSL and rebuild. However, infrastructure configs (Docker, Terraform) can be customized.

**Q: How do I add a new field?**
A: Edit the entity in your DSL file, then run `dazzle build`.

**Q: My build is slow**
A: Use `dazzle build --incremental` for faster rebuilds when only small changes were made.

## For LLMs

When assisting with this project:
- Suggest DSL edits for behavior changes, not manual code modifications
- Regenerate artifacts after DSL changes
- Respect the DSL → IR → Backend → Code pipeline
- Keep business logic in DSL, not scattered in generated files
"""


def generate_dazzle_primer() -> str:
    """Generate .llm/DAZZLE_PRIMER.md content."""
    return """# DAZZLE Primer for LLMs

This document provides a comprehensive overview of DAZZLE for AI assistants.

## Core Concepts

### 1. DSL (Domain-Specific Language)
DAZZLE uses a declarative DSL to define:
- **Entities**: Domain models (e.g., User, Order, Product)
- **Surfaces**: UI entry points (list, view, create, edit)
- **Experiences**: Multi-step flows (e.g., checkout, onboarding)
- **Services**: External integrations and business logic
- **Integrations**: Connections to third-party APIs

### 2. AppSpec IR (Intermediate Representation)
The DSL is parsed into an immutable IR called `AppSpec`:
- Language-agnostic representation of the application
- Validated and linked across modules
- Single source consumed by all backends

### 3. DNR Frontend
The Dazzle Runtime uses server-rendered HTMX templates:
- Jinja2 templates produce HTML with `hx-*` attributes
- HTMX handles server interactions (search, forms, pagination)
- Alpine.js manages ephemeral UI state (toggles, selections, transitions)
- DaisyUI provides Tailwind CSS components
- No build step — three CDN script tags, zero node_modules

### 4. Backends
Backends generate concrete artifacts from AppSpec:
- `django_api` → Django REST Framework
- `nextjs_frontend` → Next.js app with TypeScript
- `openapi` → OpenAPI 3.0 specification
- `docker` → Docker Compose setup
- `terraform` → Terraform infrastructure

### 5. Stacks
Stacks are preset combinations of backends:
- `django_next` → Django + Next.js + Docker
- `api_only` → Django API + OpenAPI + Docker
- Custom stacks can be defined in `dazzle.toml`

### 6. Project Manifest (dazzle.toml)
Configuration file specifying:
- Project metadata (name, version)
- Module paths (where DSL files live)
- Stack selection
- Backend-specific settings
- Infrastructure configuration

## File Types and Roles

| Path | Type | Role | Edit? |
|------|------|------|-------|
| `dsl/*.dsl` | DSL source | Application definition | ✅ YES |
| `dazzle.toml` | Manifest | Project configuration | ✅ YES |
| `build/**` | Generated | Backend output | ❌ NO (regenerate) |
| `infra/**` | Generated | Infrastructure templates | ⚠️ CAREFULLY |

## Editing Rules

### When to Edit DSL
- Adding/removing entities
- Changing field types or constraints
- Modifying relationships
- Adding new surfaces or experiences
- Changing business logic

### When to Edit dazzle.toml
- Changing stack configuration
- Selecting different backends
- Configuring Docker settings
- Adjusting infrastructure parameters

### When to Regenerate
After any DSL or manifest change:
```bash
dazzle build
```

This is **idempotent** and **safe** — generated code is deterministic.

## DSL Syntax Overview

### Entity Definition
```
entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  created_at: datetime auto_add
```

### Surface Definition
```
surface user_list "User List":
  uses entity User
  mode: list

  section main "Users":
    field email "Email"
    field name "Name"
```

### Field Types
- `str(N)` → String with max length
- `text` → Long text
- `int`, `float`, `decimal` → Numbers
- `bool` → Boolean
- `date`, `datetime`, `time` → Temporal
- `uuid` → UUID
- `email`, `url` → Specialized strings
- `enum[a,b,c]` → Enumeration
- `ref[Entity]` → Foreign key

### Field Modifiers
- `required` → Not null
- `unique` → Unique constraint
- `pk` → Primary key
- `auto_add` → Auto-set on creation
- `auto_update` → Auto-update on modification
- `=value` → Default value

## Backend Output

### Django Backend (django_api)
Generates:
- `models.py` → Django models from entities
- `serializers.py` → DRF serializers
- `views.py` → DRF viewsets from surfaces
- `urls.py` → URL routing
- `settings.py` → Django configuration
- `migrations/` → Database migrations

### OpenAPI Backend (openapi)
Generates:
- `openapi.yaml` → Complete API specification
- Includes schemas, paths, responses

### Infrastructure Backends
- `docker` → Dockerfile, compose.yaml
- `terraform` → Terraform modules for AWS

## Common Patterns

### 1. Adding a New Field
```diff
entity User "User":
  id: uuid pk
  email: str(255) required unique
+ phone: str(20)
```
Then: `dazzle build`

### 2. Creating Relationships
```
entity Order "Order":
  id: uuid pk
  user: ref[User] required
  items: ref[OrderItem]
```

### 3. Changing Stack
In `dazzle.toml`:
```toml
[stack]
name = "django_next"  # or "api_only", or custom
```

## Troubleshooting

### DSL Validation Errors
```bash
dazzle validate
```
Read error messages carefully — they indicate exactly what's wrong.

### Build Errors
```bash
dazzle build --backend openapi  # Test one backend
dazzle build --force             # Force full rebuild
```

### Viewing Generated Code
```bash
ls build/
cat build/django_api/api/models.py
```

## Best Practices

1. **Keep DSL minimal** — Only domain logic, no framework details
2. **One entity per concept** — Don't over-normalize in DSL
3. **Use surfaces wisely** — Map to actual UI needs
4. **Validate often** — Catch errors early
5. **Regenerate frequently** — Stay in sync with DSL

## Anti-Patterns

❌ Editing generated code directly (it will be overwritten)
❌ Duplicating logic between DSL and generated code
❌ Embedding SQL/API details in DSL
❌ Skipping validation before building
❌ Committing `build/` to version control (unless intentional)

## For More Information

- Run `dazzle --help` for CLI reference
- Check `dazzle backends` for available backends
- Use `dazzle demo --list` to see example stacks
"""


def generate_claude_project_context(project_name: str, stack_name: str | None = None) -> str:
    """Generate .claude/PROJECT_CONTEXT.md content."""
    stack_info = f"**Stack**: `{stack_name}`\n\n" if stack_name else ""

    return f"""# Claude Project Context: {project_name}

{stack_info}This is a DAZZLE-generated project. DAZZLE is a DSL-first application generator that transforms
domain specifications into production code.

## Your Role

When helping with this project:

1. **Prefer DSL edits** over manual code changes
   - User wants to add a field? → Suggest editing `dsl/*.dsl`
   - User wants to change an entity? → Update the DSL definition
   - User wants different behavior? → Check if it's expressible in DSL first

2. **Keep code aligned with DSL**
   - Generated code in `build/` should match DSL
   - Don't hand-edit generated files unless user explicitly requests it
   - After DSL changes, remind user to run `dazzle build`

3. **Avoid destructive operations**
   - Don't delete `dsl/` files without confirmation
   - Don't modify `dazzle.toml` without understanding impact
   - Be cautious with infrastructure changes

4. **Suggest safe workflows**
   - Edit DSL → Validate → Build → Test
   - Use `dazzle validate` before building
   - Use `dazzle build --diff` to preview changes

## Project Structure

```
{project_name}/
├── dsl/                    ← Source of truth (edit here)
├── dazzle.toml            ← Configuration (edit here)
├── build/                 ← Generated code (regenerate, don't edit)
└── LLM_CONTEXT.md         ← Overview for all LLMs
```

## Safe Interactions

### When User Asks to Add/Change Features
1. First, check if it's a DSL concern (entities, fields, surfaces)
2. If yes: Suggest DSL edits
3. If no: Check if it's in `dazzle.toml` (stack, backends)
4. If neither: It might need custom code in designated extension points

### When User Reports Bugs
1. Check if generated code is out of sync with DSL
2. Suggest `dazzle build --force` to regenerate
3. Look for validation errors: `dazzle validate`
4. If the bug is confirmed, file it on GitHub: `gh issue create --repo manwithacat/dazzle`
   (If `gh` is not authenticated, run `gh auth login` first)

### When Generating New Code
1. Follow DAZZLE conventions (check existing generated code)
2. Match patterns used by backends
3. Don't mix hand-written and generated code without clear separation

### When Unclear
1. Inspect `dsl/*.dsl` to understand domain model
2. Check `dazzle.toml` for configuration
3. Read `.llm/DAZZLE_PRIMER.md` for DAZZLE concepts
4. Ask user if change should be in DSL or custom code

## Commands You Can Run

✅ Safe (run without approval):
- `dazzle validate`
- `dazzle build`
- `dazzle build --diff`
- `git status`, `git diff`
- `ls`, `cat`
- `python manage.py check` (if Django)

⚠️ Require confirmation:
- `dazzle build --force` (overwrites everything)
- `docker compose up -d` (starts services)
- `terraform apply` (deploys infrastructure)

❌ Avoid:
- `rm -rf` anything
- `terraform destroy` (without explicit request)
- Editing files in `build/` directly

## DAZZLE Workflow Reminders

After DSL changes:
```bash
dazzle validate   # Check for errors
dazzle build      # Regenerate code
```

After configuration changes:
```bash
dazzle build --force  # Full rebuild
```

When testing:
```bash
cd build/django_api && python manage.py runserver  # If Django
cd build/docker && docker compose up         # If Docker
```

## This Project's Specifics

- **Primary DSL module**: `dsl/` directory
- **Generated artifacts**: `build/` directory
- **Truth source**: `dsl/*.dsl` and `dazzle.toml`

Always prioritize keeping the DSL as the source of truth.
"""


def generate_claude_permissions() -> str:
    """Generate .claude/permissions.json content."""
    return """{
  "allowedCommands": [
    "Bash(git *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(grep *)",
    "Bash(find *)",
    "Bash(python3 *)",
    "Bash(pip *)",
    "Bash(dazzle *)",
    "Bash(docker ps *)",
    "Bash(docker logs *)",
    "Bash(docker images *)",
    "Bash(pytest *)",
    "Bash(tree *)",
    "Bash(curl *)",
    "Bash(wget *)"
  ],
  "deniedCommands": [
    "Bash(rm -rf /*)",
    "Bash(terraform destroy *)"
  ],
  "requireApproval": [
    "Bash(docker compose up *)",
    "Bash(docker compose down *)",
    "Bash(docker system prune *)",
    "Bash(terraform apply *)",
    "Bash(terraform init *)",
    "Bash(npm install *)",
    "Bash(pip install *)"
  ]
}
"""


def generate_copilot_context(project_name: str) -> str:
    """Generate .copilot/CONTEXT.md content."""
    return f"""# GitHub Copilot Context: {project_name}

This repository is **DAZZLE-generated**. DAZZLE is a DSL-first framework that generates
production code from domain specifications.

## For Copilot

### When Proposing Edits

**Prefer modifying DSL** over hand-editing generated code:
- User wants to add a field → Suggest editing `dsl/*.dsl`
- User wants to change behavior → Check if it's in the DSL first
- User wants new entities → Add to DSL, then `dazzle build`

### Generated vs Hand-Written

- `dsl/*.dsl` → **Source of truth** (edit this)
- `dazzle.toml` → **Configuration** (edit this)
- `build/` → **Generated code** (regenerate via `dazzle build`, don't hand-edit)

### Workflow

1. User edits DSL or manifest
2. Run `dazzle validate` to check
3. Run `dazzle build` to regenerate
4. Test the changes

### Code Patterns to Follow

When suggesting code:
- **Match existing generated patterns** (check `build/` for style)
- **Align API shapes with DSL entities** (follow entity → model → API pipeline)
- **Follow DAZZLE conventions** (don't mix frameworks or patterns)

### What This Repo Contains

Business logic is in **DSL files**, not framework code. Generated code implements
the DSL specification using selected backends (Django, Next.js, etc.).

Don't suggest:
- Duplicating entity definitions in code
- Embedding DSL logic in generated files
- Framework-specific workarounds when DSL can express it

Do suggest:
- DSL improvements for new requirements
- Custom extensions in designated areas
- Infrastructure tweaks in `build/infra_*`

### Example Interaction

**User**: "Add a 'phone' field to User"

**Good response**:
```
Edit dsl/users.dsl:

entity User "User":
  ...
  phone: str(20)

Then run: dazzle build
```

**Bad response**:
```
Edit build/django_api/models.py:

class User(models.Model):
    phone = models.CharField(max_length=20)
```

(This will be overwritten on next build!)

## Summary

- Repository is DAZZLE-generated
- DSL = source of truth
- Edit DSL, not generated code
- Follow regeneration workflow
- Match existing patterns when adding custom code
"""


def create_llm_instrumentation(
    project_dir: Path,
    project_name: str,
    stack_name: str | None = None,
) -> None:
    """
    Create all LLM context files in a project directory.

    Args:
        project_dir: Root directory of the project
        project_name: Name of the project
        stack_name: Optional stack name being used
    """
    # Create root LLM_CONTEXT.md
    (project_dir / "LLM_CONTEXT.md").write_text(
        generate_llm_context_md(project_name, stack_name), encoding="utf-8"
    )

    # Create .llm/ directory and DAZZLE_PRIMER.md
    llm_dir = project_dir / ".llm"
    llm_dir.mkdir(exist_ok=True)
    (llm_dir / "DAZZLE_PRIMER.md").write_text(generate_dazzle_primer(), encoding="utf-8")

    # Create .claude/ directory and files
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "PROJECT_CONTEXT.md").write_text(
        generate_claude_project_context(project_name, stack_name), encoding="utf-8"
    )
    (claude_dir / "permissions.json").write_text(generate_claude_permissions(), encoding="utf-8")

    # Create MCP server configuration
    import json

    mcp_config = {
        "mcpServers": {
            "dazzle": {
                "command": "dazzle",
                "args": ["mcp", "--working-dir", "${projectDir}"],
                "env": {},
                "autoStart": True,
            }
        }
    }
    (claude_dir / "mcp.json").write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")

    # Create .copilot/ directory and CONTEXT.md
    copilot_dir = project_dir / ".copilot"
    copilot_dir.mkdir(exist_ok=True)
    (copilot_dir / "CONTEXT.md").write_text(
        generate_copilot_context(project_name), encoding="utf-8"
    )


__all__ = [
    "create_llm_instrumentation",
    "generate_llm_context_md",
    "generate_dazzle_primer",
    "generate_claude_project_context",
    "generate_claude_permissions",
    "generate_copilot_context",
]
