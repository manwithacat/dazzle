# Dazzle Second Evolutionary Bottleneck DSL – Practical Design Recommendations (v1)

You are an expert developer agent working inside the Dazzle ecosystem. Your goal is to introduce a **second evolutionary bottleneck** – a *Design Pattern DSL* (DP-DSL) – that sits between the **Domain DSL** (high-level, problem-space spec) and the **Core Implementation DSL** (token-efficient, compiler-facing spec).

Your job is to:
- Keep build flows token-efficient and predictable for LLMs.
- Avoid overfitting to any single runtime stack.
- Capture reusable architectural patterns explicitly (factories, adapters, ports-and-adapters, CQRS, etc.).
- Preserve the **core Dazzle DSL** as the ultimate ground truth for compilation.

Follow these imperatives precisely.

---

## 1. Introduce the Design Pattern DSL as a Separate File

1. **Create a dedicated DP-DSL file per app**
   - File path (recommended):
     - `dazzle/design/app_patterns.dp.yml`
   - Treat this file as the *only* place where high-level design patterns are declared in a structured way.

2. **Never embed design patterns directly in the Domain DSL**
   - Keep the Domain DSL focused on:
     - Business concepts.
     - Roles, workflows, permissions.
     - Data entities and user journeys.
   - Use the DP-DSL to describe:
     - Which design patterns should shape the implementation.
     - How those patterns bind onto Domain DSL entities and operations.

3. **Always ensure DP-DSL compiles to Core DSL**
   - Design the DP-DSL so that:
     - Each pattern declaration deterministically expands into **core Dazzle DSL** fragments.
     - No DP-DSL construct requires modifying the core DSL.
   - You MUST always be able to produce a core-only artifact such as:
     - `dazzle/build/app_core_dsl.yml`

---

## 2. Define a Minimal, Extensible Pattern Vocabulary

1. **Start with a bounded set of canonical patterns**
   - You MUST support, at minimum, the following pattern families:
     - `factory` (and `abstract_factory`)
     - `strategy`
     - `adapter`
     - `facade`
     - `observer` / `pubsub`
     - `repository`
     - `service` (application service / use case)
     - `ports_and_adapters` (a.k.a. hexagonal)
     - `cqrs` (read/write segregation)
     - `saga` / `process_manager` (for multi-step workflows)
   - Represent each pattern family by a **pattern kind** and **role types**.

2. **Represent patterns in a generic, stack-neutral way**
   - Do NOT assume:
     - A specific language (e.g. TypeScript, Python).
     - A specific framework (e.g. Django, NestJS).
   - Use neutral terms:
     - `port`, `adapter`, `domain_model`, `application_service`, `infrastructure_adapter`, `event_handler`, etc.

3. **Example DP-DSL schema fragment**
   - Use a structure like:

```yaml
patterns:
  - id: "user_registration_flow"
    kind: "ports_and_adapters"
    applies_to:
      domain_use_case: "user.register"
    ports:
      - name: "user_repository"
        role: "outbound"
        contract: "UserRepository"
      - name: "email_notification"
        role: "outbound"
        contract: "EmailNotifier"
    policies:
      transaction_boundary: "use_case"
      validation_strategy: "strategy"
      error_surface: "domain_error"
```

   - Ensure every field is:
     - Machine-parseable.
     - Deterministically mappable into core DSL constructs.

---

## 3. Map the Three-Layer Flow Explicitly

You MUST structure generation around three distinct layers:

1. **Domain DSL → DP-DSL**
   - Read the Domain DSL file(s), e.g.:
     - `dazzle/domain/app_domain.dsl.yml`
   - Infer:
     - Entities.
     - Use cases / commands / queries.
     - External systems and actors.
   - For each non-trivial use case:
     - Choose appropriate patterns (`service`, `ports_and_adapters`, `cqrs`, etc.).
     - Emit a DP-DSL entry that describes:
       - The pattern kind.
       - The domain element it binds to.
       - Any ports, repositories, strategies, or events.

2. **DP-DSL → Core Implementation DSL**
   - For each DP-DSL entry:
     - Generate one or more core DSL fragments that:
       - Declare services, handlers, repositories, and adapters.
       - Wire ports to infrastructure contracts.
       - Define boundaries (transactions, events, error contracts).
   - Merge all pattern-derived fragments into:
     - `dazzle/build/app_core_dsl.yml`

3. **Core Implementation DSL → Concrete Code**
   - Downstream generators or agents consume `app_core_dsl.yml` to:
     - Emit framework- or language-specific code.
   - You MUST NOT leak framework-specific details back into Domain DSL or DP-DSL.

---

## 4. Practical Design Recommendations – Detailed Proposal

1. **Keep DP-DSL deliberately small and composable**
   - Restrict the initial DP-DSL to a **small core** of pattern constructs:
     - `kind` – the pattern family (e.g. `factory`, `ports_and_adapters`).
     - `applies_to` – references to Domain DSL elements.
     - `roles` – internal roles like `port`, `adapter`, `strategy`, `observer`.
     - `policies` – cross-cutting choices (e.g. transaction boundaries, caching, logging).
   - Avoid embedding low-level details (e.g. HTTP verbs, database schema) here; those belong in core DSL.

2. **Model evolutionary pressure via DP-DSL, not code**
   - When a given architectural shape recurs across multiple apps:
     - Add or refine a DP-DSL pattern.
     - DO NOT hardwire the shape directly in generated code.
   - Example:
     - If many apps need “event-driven read models,” introduce a `cqrs` + `observer` combination in DP-DSL instead of hand-wiring event consumers each time.

3. **Tie pattern selection to measurable heuristics**
   - Design the agent to choose patterns based on:
     - **Complexity** of the use case (number of steps, external dependencies).
     - **Volatility** of requirements (areas likely to change → prefer strategy / ports).
     - **Integration** needs (number of external systems → prefer adapters and ports).
   - Example heuristics:
     - If a use case touches ≥ 2 external systems → use `ports_and_adapters`.
     - If a piece of business logic has ≥ 2 configurable algorithms → use `strategy`.

4. **Make DP-DSL token-efficient and LLM-friendly**
   - Use:
     - Short, consistent keys.
     - Explicit references instead of prose.
   - Avoid:
     - Long natural language blocks.
     - Redundant repetition of domain descriptions.
   - Encourage:
     - Pattern IDs and domain references that are easy to autocomplete and path-complete.

5. **Keep a clear mapping index between Domain DSL and DP-DSL**
   - Always maintain a machine-readable mapping file, e.g.:
     - `dazzle/design/domain_mapping.yml`
   - Include entries like:

```yaml
use_cases:
  - domain_id: "user.register"
    dp_pattern_ids:
      - "user_registration_flow"
      - "user_registration_notifications"
entities:
  - domain_id: "invoice"
    dp_pattern_ids:
      - "invoice_repository"
      - "invoice_read_model_projection"
```

   - Use this mapping to:
     - Avoid drift.
     - Enable refactoring across layers.
     - Help higher-level agents reason about the architecture.

6. **Separate DP-DSL concerns from local vocabulary (macro) system**
   - Keep **app-local vocabulary** (macros / aliases) in:
     - `dazzle/local_vocab/manifest.yml`
   - Keep **architectural pattern shaping** in:
     - `dazzle/design/app_patterns.dp.yml`
   - DO NOT mix:
     - Pattern semantics (DP-DSL).
     - Syntactic sugar for core DSL (local vocab).
   - You MAY allow:
     - Local vocabulary entries that expand into pattern-shaped core fragments, but they must still consume the DP-DSL outputs or references, not override them.

7. **Support multiple implementation backends from the same DP-DSL**
   - Always structure DP-DSL so it can drive more than one backend template:
     - Example backends:
       - `django_rest_backend`
       - `fastapi_async_backend`
       - `node_nest_backend`
   - Ensure:
     - The DP-DSL does not include backend-specific keys.
     - Backend selection is configured separately (e.g. in `dazzle/build/config.yml`).

8. **Emit rich, but compact, metadata for future mining**
   - For each DP-DSL pattern entry, include:
     - `tags`: like `["auth", "billing", "notification", "reporting"]`.
     - `complexity`: rough heuristic (`"low" | "medium" | "high"`).
     - `change_risk`: e.g. `"stable" | "volatile"`.
   - Example:

```yaml
  metadata:
    tags: ["auth", "user_management"]
    complexity: "medium"
    change_risk: "volatile"
```

   - Use these fields so that:
     - Future agents can cluster similar patterns.
     - Dazzle can propose new high-level pattern abstractions.

9. **Validate DP-DSL before expansion**
   - Implement a validation step before generating core DSL:
     - Check that:
       - All `applies_to` references point to existing Domain DSL elements.
       - All required roles (e.g. a `ports_and_adapters` pattern must have at least one outbound `port`) are present.
       - Policies are set to valid, predefined values.
   - On any validation failure:
     - Emit a machine-readable error file, e.g. `dazzle/build/dp_validation_errors.json`.
     - Do NOT generate or overwrite `app_core_dsl.yml`.

10. **Document the pattern layer for humans**
    - Always add a short design section to the repo, e.g.:
      - `dazzle/DESIGN_PATTERNS.md`
    - Include:
      - A brief explanation of the DP-DSL and its purpose as an evolutionary bottleneck.
      - A list of patterns currently used in the app with a one-line description.
      - Pointers to the actual DP-DSL file.

---

## 5. Agent Workflow Summary

When operating as the Dazzle expert developer agent, follow this workflow:

1. **Ingest Domain DSL**
   - Read domain files.
   - Extract use cases, entities, and integrations.

2. **Emit / Update DP-DSL**
   - Choose patterns for each significant use case and entity.
   - Write or update `dazzle/design/app_patterns.dp.yml`.
   - Maintain `dazzle/design/domain_mapping.yml`.

3. **Validate DP-DSL**
   - Run structural and referential checks.
   - If invalid, emit errors and STOP.

4. **Generate Core Implementation DSL**
   - Expand DP-DSL into core DSL fragments.
   - Merge into `dazzle/build/app_core_dsl.yml`.

5. **Coordinate with Local Vocabulary**
   - Optionally define app-local vocabulary entries to wrap common pattern-based fragments.
   - Ensure these always expand into valid core DSL that is itself derived from the DP-DSL decisions.

6. **Support Multiple Backends**
   - Use `app_core_dsl.yml` and a separate backend configuration to generate concrete code.
   - Never bake backend specifics into Domain or DP-DSL.

By following these imperatives, you maintain a clean, token-efficient pathway from domain description to implementation while capturing architectural design patterns explicitly in a separate evolutionary bottleneck. This allows Dazzle to evolve its design vocabulary over time without destabilising existing apps or over-coupling to any single technical stack.
