# Next.js Onebox Stack - Bug Fix Implementation Plan

**Date**: 2025-11-25
**Source**: `/Volumes/SSD/support_tickets/dev_docs/dazzle_feedback.md`
**Priority**: Critical - Multiple showstopper bugs

---

## Executive Summary

The `nextjs_onebox` stack has **9 critical/high severity bugs** that prevent generated code from building or running. This plan prioritizes fixes in dependency order, starting with foundational issues (Prisma schema, types) before UI issues (JSX, Tailwind).

---

## Phase 1: Critical Foundational Fixes (Showstoppers)

These must be fixed first as they block all subsequent testing.

### 1.1 Fix Prisma Schema Generation (#3) - CRITICAL

**File**: `src/dazzle/stacks/nextjs_onebox/generators/prisma.py`

**Issues**:
1. Duplicate User model (built-in auth + DSL-defined User)
2. Invalid relation syntax (missing FK fields and @relation directives)
3. Wrong index field names (snake_case instead of camelCase with Id suffix)

**Implementation**:

```python
# 1. Detect User collision
def generate_schema(appspec: ir.AppSpec) -> str:
    # Check if DSL defines a User entity
    user_entity = next((e for e in appspec.entities if e.name == "User"), None)

    if user_entity:
        # Merge DSL User fields into built-in auth User
        merged_user = merge_user_entity(user_entity)
    else:
        # Use default auth User
        merged_user = get_default_auth_user()

    # Generate other models...

# 2. Fix relation generation
def generate_field(field: ir.FieldSpec, entity_name: str) -> str:
    if field.field_type == ir.FieldType.REFERENCE:
        # Generate FK + relation pair
        fk_name = f"{field.name}Id"
        relation_name = f"{entity_name}{field.name.title()}"

        return f"""
  {fk_name} String{' @db.Uuid' if field.is_required else '? @db.Uuid'}
  {field.name}   {field.type_ref}{'' if field.is_required else '?'}   @relation("{relation_name}", fields: [{fk_name}], references: [id])
"""
    # ... other field types

# 3. Fix index generation
def generate_indexes(entity: ir.EntitySpec) -> list[str]:
    indexes = []
    for constraint in entity.constraints:
        if constraint.kind == ir.ConstraintKind.INDEX:
            # Transform field names: relation fields need "Id" suffix
            field_names = []
            for field_name in constraint.fields:
                field = next(f for f in entity.fields if f.name == field_name)
                if field.field_type == ir.FieldType.REFERENCE:
                    field_names.append(f"{field_name}Id")
                else:
                    field_names.append(field_name)

            indexes.append(f"@@index([{', '.join(field_names)}])")
    return indexes
```

**Test Cases**:
- DSL with User entity → single merged User model
- Multiple refs to same entity → named relations
- Indexes on relation fields → correct FK field names

---

### 1.2 Fix TypeScript Types to Match Prisma (#9) - CRITICAL

**File**: `src/dazzle/stacks/nextjs_onebox/generators/types.py`

**Issue**: Types use DSL relation names (`ticket`, `author`) instead of Prisma FK names (`ticketId`, `authorId`)

**Implementation**:

```python
def generate_entity_type(entity: ir.EntitySpec) -> str:
    fields = []

    for field in entity.fields:
        if field.field_type == ir.FieldType.REFERENCE:
            # Generate FK field, not relation field
            fk_name = f"{field.name}Id"
            ts_type = "string" + ("" if field.is_required else " | null")
            fields.append(f"  {fk_name}: {ts_type};")
        else:
            # Regular field
            ts_type = map_dsl_type_to_ts(field.type_name)
            if not field.is_required:
                ts_type += " | null"
            fields.append(f"  {field.name}: {ts_type};")

    return f"export interface {entity.name} {{\n" + "\n".join(fields) + "\n}"
```

---

### 1.3 Fix next.config.ts → next.config.mjs (#5) - CRITICAL

**File**: `src/dazzle/stacks/nextjs_onebox/generators/config.py`

**Issue**: Next.js 14 doesn't support TypeScript config files

**Implementation**:

```python
def generate_next_config(appspec: ir.AppSpec) -> tuple[Path, str]:
    content = """/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
};

export default nextConfig;
"""
    return Path("next.config.mjs"), content  # Changed from .ts
```

---

### 1.4 Fix Invalid JSX Syntax in Forms (#7) - CRITICAL

**File**: `src/dazzle/stacks/nextjs_onebox/generators/pages.py`

**Issues**:
1. Create forms: `defaultValue={}` → should be `defaultValue=""`
2. Edit forms: `defaultValue={item.` → incomplete, needs field name
3. Checkboxes: `defaultChecked={}` → should be `defaultChecked={false}`

**Implementation**:

```python
def generate_form_field(field: ir.FieldSpec, mode: str, entity_name: str) -> str:
    """Generate JSX for a form field.

    Args:
        field: Field specification
        mode: "create" or "edit"
        entity_name: Name of entity (for relation lookups)
    """
    if mode == "create":
        # Use empty string or DSL default
        if field.field_type == ir.FieldType.BOOLEAN:
            default = "false" if not field.default_value else str(field.default_value).lower()
            return f'<input type="checkbox" defaultChecked={{{default}}} />'
        else:
            default = f'"{field.default_value}"' if field.default_value else '""'
            return f'<Input defaultValue={{{default}}} />'

    elif mode == "edit":
        # Use item.fieldName with nullish coalescing
        if field.field_type == ir.FieldType.REFERENCE:
            field_name = f"{field.name}Id"  # Use FK field name
        else:
            field_name = field.name

        if field.field_type == ir.FieldType.BOOLEAN:
            return f'<input type="checkbox" defaultChecked={{item.{field_name} ?? false}} />'
        elif field.field_type == ir.FieldType.NUMBER:
            return f'<Input type="number" defaultValue={{item.{field_name}?.toString() ?? ""}} />'
        else:
            return f'<Input defaultValue={{item.{field_name} ?? ""}} />'
```

---

### 1.5 Fix Tailwind CSS Color Variables (#8) - CRITICAL

**File**: `src/dazzle/stacks/nextjs_onebox/generators/styles.py`

**Issue**: `globals.css` uses `@apply border-border` but `tailwind.config.ts` doesn't define the border color

**Implementation**:

```python
def generate_tailwind_config(appspec: ir.AppSpec) -> str:
    content = """import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
      },
    },
  },
  plugins: [],
};

export default config;
"""
    return content
```

---

## Phase 2: High Priority Type Fixes

### 2.1 Fix React 19 useActionState Compatibility (#10)

**File**: `src/dazzle/stacks/nextjs_onebox/generators/pages.py`

**Issue**: Using React 19's `useActionState` with React 18

**Options**:
1. Upgrade to React 19
2. Use React 18's `useFormState` from `react-dom`

**Recommendation**: Use React 18 compatible version for stability

```python
def generate_form_imports() -> str:
    return """import { useFormState } from "react-dom";  // React 18 compatible
import { useFormStatus } from "react-dom";
"""
```

---

### 2.2 Fix Prisma QueryMode Type Error (#11)

**File**: `src/dazzle/stacks/nextjs_onebox/generators/actions.py`

**Issue**: String literal needs `as const` assertion

**Implementation**:

```python
def generate_search_filter(field: ir.FieldSpec) -> str:
    if field.field_type == ir.FieldType.STRING:
        return f"""{{
  {field.name}: {{
    contains: query,
    mode: "insensitive" as const,
  }},
}}"""
```

---

## Phase 3: Configuration & Dependencies

### 3.1 Update npm Dependencies (#2)

**File**: `src/dazzle/stacks/nextjs_onebox/generators/config.py`

**Current (deprecated)**:
```json
"eslint": "^8.57.0",
"eslint-config-next": "^14.2.0"
```

**Updated**:
```json
"eslint": "^9.15.0",
"eslint-config-next": "^15.0.0"
```

**Also update**:
- React 18.3.0 → 18.3.1 (or 19.0.0 if using useActionState)
- Other dependencies to latest stable

---

### 3.2 Add docker-compose.yml for Local Dev (#4)

**File**: `src/dazzle/stacks/nextjs_onebox/generators/docker.py`

**Add separate development compose file**:

```python
def generate_docker_compose_dev(appspec: ir.AppSpec) -> tuple[Path, str]:
    content = f"""version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {appspec.app_name}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
"""
    return Path("docker-compose.dev.yml"), content
```

**Update README with**:
```bash
# Local development with Docker
docker-compose -f docker-compose.dev.yml up -d
npm install
npm run db:generate
npm run db:push
npm run dev
```

---

## Phase 4: Testing & Validation

### 4.1 Automated Build Testing

Add to CI/CD:

```bash
#!/bin/bash
# test_nextjs_onebox.sh

set -e

# Generate test project
cd /tmp
dazzle init test_nextjs --from support_tickets
cd test_nextjs

# Build with nextjs_onebox stack
dazzle build --stack nextjs_onebox

# Navigate to generated code
cd build/support_tickets

# Install dependencies
npm install

# Run type checking
npm run type-check || npx tsc --noEmit

# Run linting
npm run lint

# Generate Prisma client
npm run db:generate

# Try to build
npm run build

echo "✓ All tests passed"
```

---

## Phase 5: Enhancements (Post-Critical Fixes)

### 5.1 Generate Static/Marketing Pages (#17)

Lower priority but valuable for professional UX.

**Approach**: Hybrid template-based generation

```python
def generate_marketing_pages(appspec: ir.AppSpec) -> dict[Path, str]:
    pages = {}

    # Home/landing page
    pages[Path("src/app/page.tsx")] = generate_home_page(appspec)

    # About page
    pages[Path("src/app/about/page.tsx")] = generate_about_page(appspec)

    # Help/documentation
    pages[Path("src/app/help/page.tsx")] = generate_help_page(appspec)

    # Legal boilerplate (with TODO markers)
    pages[Path("src/app/terms/page.tsx")] = generate_terms_template(appspec)
    pages[Path("src/app/privacy/page.tsx")] = generate_privacy_template(appspec)

    return pages

def generate_home_page(appspec: ir.AppSpec) -> str:
    # Extract features from entities
    features = []
    for entity in appspec.entities:
        if entity.description:
            features.append({
                "title": f"{entity.name} Management",
                "description": entity.description,
            })

    # Generate Hero + Features layout
    return render_home_template(
        title=appspec.title,
        description=appspec.description or "Generated with DAZZLE",
        features=features,
    )
```

---

## Implementation Order

1. **Day 1** (Critical Path):
   - Fix Prisma schema generation (#3)
   - Fix TypeScript types (#9)
   - Fix next.config.mjs (#5)

2. **Day 2** (UI Fixes):
   - Fix JSX syntax in forms (#7)
   - Fix Tailwind colors (#8)
   - Fix QueryMode type (#11)

3. **Day 3** (Configuration):
   - Fix React compatibility (#10)
   - Update npm dependencies (#2)
   - Add docker-compose.dev.yml (#4)

4. **Day 4** (Testing):
   - Add automated build tests
   - Test all examples with nextjs_onebox stack
   - Verify Docker builds and runs

5. **Day 5** (Enhancements):
   - Generate marketing pages (#17)
   - Add better post-build instructions
   - Documentation improvements

---

## Success Criteria

### Must Have (Blocking Release)
- ✅ Generated code builds without errors (`npm run build` succeeds)
- ✅ Type checking passes (`tsc --noEmit` succeeds)
- ✅ No invalid JSX syntax
- ✅ Prisma schema is valid
- ✅ Types match Prisma schema

### Should Have (Important)
- ✅ No deprecated npm package warnings
- ✅ Docker compose for local dev
- ✅ React 18 compatibility
- ✅ All example projects build successfully

### Nice to Have (Enhancements)
- ✅ Marketing/static pages
- ✅ Better post-build instructions
- ✅ Automated integration tests

---

## Risk Assessment

**High Risk**:
- Prisma schema changes may break existing projects
- Type system changes may require regeneration
- React version conflicts

**Mitigation**:
- Add version detection for backward compatibility
- Create migration guide for existing projects
- Test with both React 18 and 19

**Low Risk**:
- Config file rename (next.config.ts → .mjs)
- Tailwind color variables
- npm dependency updates

---

## Files to Modify

1. `src/dazzle/stacks/nextjs_onebox/generators/prisma.py` - Schema generation
2. `src/dazzle/stacks/nextjs_onebox/generators/types.py` - TypeScript types
3. `src/dazzle/stacks/nextjs_onebox/generators/config.py` - next.config.mjs, package.json
4. `src/dazzle/stacks/nextjs_onebox/generators/pages.py` - JSX syntax, React hooks
5. `src/dazzle/stacks/nextjs_onebox/generators/styles.py` - Tailwind config
6. `src/dazzle/stacks/nextjs_onebox/generators/actions.py` - QueryMode type
7. `src/dazzle/stacks/nextjs_onebox/generators/docker.py` - docker-compose.dev.yml

---

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_nextjs_onebox_prisma.py
def test_no_user_collision():
    """Test that User entity merges with auth User."""
    appspec = create_test_appspec_with_user()
    schema = generate_prisma_schema(appspec)
    assert schema.count("model User {") == 1

def test_relation_syntax():
    """Test that relations use proper FK + @relation syntax."""
    appspec = create_test_appspec_with_relations()
    schema = generate_prisma_schema(appspec)
    assert "createdById String @db.Uuid" in schema
    assert '@relation("TicketCreatedBy"' in schema
```

### Integration Tests
```bash
# Run full build test
pytest tests/integration/test_nextjs_onebox_build.py -v
```

---

## Next Steps

1. Review and approve this plan
2. Create feature branch: `fix/nextjs-onebox-critical-bugs`
3. Implement Phase 1 (critical fixes)
4. Test with support_tickets example
5. Iterate on remaining phases

---

**Status**: Plan Complete - Ready for Implementation
**Estimated Effort**: 3-5 days for critical fixes + testing
**Priority**: P0 - Blocking production use of nextjs_onebox stack
