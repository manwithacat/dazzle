# DAZZLE Stacks & Full-Stack Generation Strategy
## (LLM-Facing Implementation Brief)

This document gives explicit, imperative instructions for an LLM acting as an expert Python developer.
Your task is to implement DAZZLE “stacks” that allow users to generate contemporary full‑stack environments (e.g., **Next.js + Django**) without polluting the DSL or IR with infrastructure details.

You must follow the principles and design described below.

---

# 1. Keep the AppSpec Fully Infra-Agnostic

1. Do **not** modify the DSL or IR to include:
   - “django”
   - “nextjs”
   - “docker”
   - “terraform”
   - any other runtime technology

2. AppSpec must continue to define only:
   - entities
   - surfaces
   - experiences
   - services
   - foreign models
   - integrations

3. All decisions about runtime, framework, or infrastructure must be expressed only through:
   - backends,
   - the project manifest (`dazzle.toml`),
   - stack definitions.

---

# 2. Implement Backends as Atomic, Independent Modules

Create or maintain the following DAZZLE backends as separate, independently runnable codegen targets:

- `django_api`
  Generates Django + DRF (or Django-only) backend from IR.

- `nextjs_frontend`
  Generates Next.js frontend from IR + (optionally) the generated OpenAPI spec.

- `infra_docker`
  Generates Dockerfile, compose.yaml, and local dev runtime.

- `infra_terraform`
  Generates cloud infrastructure modules.

These modules must **not** depend on each other internally.
Composition happens at the **stack** level, not inside any backend.

---

# 3. Introduce Stacks as Composite Selections of Backends

Implement a “stack” system at the manifest/CLI layer.

### Example stack definition in `dazzle.toml`:

```toml
[stack]
name = "django_next"

backends = [
  "django_api",
  "nextjs_frontend",
  "infra_docker"
]
```

Rules:

1. The stack lists **ordered** backend names.
2. The CLI must read the stack and execute backends sequentially.
3. Users can override stack selection via CLI args:
   - `dazzle build --stack django_next`
   - `dazzle build --backends django_api,nextjs_frontend`

Stacks must remain simple: they are just **lists of backend identifiers**.

---

# 4. Implement “Rich Demo Environments” as First-Class Stacks

Create a special stack (or multiple stacks) intended to demonstrate DAZZLE’s full potential:

Example:

```toml
[stack]
name = "django_next_demo"

backends = [
  "django_api",
  "nextjs_frontend",
  "infra_docker"
]
```

The DAZZLE CLI must provide a user-friendly command such as:

```
dazzle demo django_next
```

which performs:

1. Writes `dazzle.toml` with `stack = "django_next_demo"`.
2. Writes a sample DAZZLE DSL (e.g., support tickets example).
3. Runs `dazzle build` to generate:
   - Django backend
   - Next.js frontend
   - Docker infra
4. Prints instructions for running `docker compose up`.

Do **not** add demo-specific constructs to the DSL.

---

# 5. Define Responsibilities of Each Backend in a Full-Stack Context

## 5.1 django_api Backend

The backend must:

1. Read the AppSpec IR.
2. Generate a Django project with:
   - models for entities
   - serializers
   - viewsets / controllers
   - routing
   - auth stubs
3. Generate an OpenAPI schema for consumption by frontend backends.

## 5.2 nextjs_frontend Backend

The backend must:

1. Consume:
   - AppSpec IR
   - OpenAPI spec from `django_api`
2. Generate a folder such as:

```
frontend/
  app/
    ...pages for surfaces and experiences
  lib/apiClient.ts
  package.json
```

3. Map IR surfaces → Next.js pages.
4. Map IR experiences → multi-step flows or navigation sequences.

The backend must **not** assume any DSL syntax changes.

## 5.3 infra_docker Backend

The backend must generate:

- Dockerfile(s)
- compose.yaml
- environment sample files
- README with instructions

Ensure:
- Django app is one service
- Next.js frontend is one service
- Postgres + Redis added if inferred from IR

## 5.4 infra_terraform Backend

The backend must generate:
- Cloud infra modules
- Environment wrappers (dev/staging/prod)
- Outputs for app URL, DB URL, queue URL
- No coupling to Docker backend

---

# 6. Provide a Simple, Accessible CLI UX

Implement the following patterns:

### Initialize a project with a stack

```
dazzle init --stack django_next
```

### Build all backends in the active stack

```
dazzle build
```

### Build a selected stack

```
dazzle build --stack django_next
```

### Build selected backends

```
dazzle build --backends django_api,nextjs_frontend
```

Stacks give users easy access to full-stack patterns **without modifying DAZZLE Core**.

---

# 7. Guidance for Presentation to Users

When designing docs and demo flows:

1. Present stacks as:
   > “Preset app layouts that combine multiple DAZZLE backends.”

2. Emphasize:
   - DSL does not change.
   - Stacks are optional and non-binding.
   - Users can mix and match backends.

3. Recommend `django_next` or `django_next_demo` as:
   - The fastest route to a production-like prototype.
   - A great way to explore DAZZLE without knowing the underlying backends.

---

# 8. Deliverables You Must Implement

1. Stack handling in the CLI:
   - Parsing stacks from `dazzle.toml`
   - Running backends in order
   - Overrides via `--stack` and `--backends`

2. Create stack presets:
   - `django_next`
   - `django_next_demo`

3. Implement `dazzle demo <stack>` command.

4. Ensure each backend behaves independently and composes cleanly when run sequentially.

5. Provide documentation describing:
   - How to use stacks
   - How to override stack defaults
   - How to select backend subsets

---

# End of Specification
