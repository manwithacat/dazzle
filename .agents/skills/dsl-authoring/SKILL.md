---
name: dsl-authoring
description: Use when writing or editing Dazzle .dsl files — syntax rules, the mistakes agents actually make, and pointers to the drift-gated references. Complements (never replaces) CLAUDE.md's DSL Quick Reference.
---

# DSL Authoring

Replaces the never-loading `dsl-patterns.md` (an `auto_load` frontmatter convention
no harness here loads — it silently rotted, ending up teaching two patterns the
footgun gates now forbid). This version stays thin on purpose: anything with a
drift-gated home is *pointed to*, not duplicated.

## Syntax rules

- **Strings**: double quotes `"like this"`, never single quotes.
- **Identifiers**: `snake_case` fields, `PascalCase` entities/surfaces.
- **Indentation**: 2-space blocks, consistent within a block.
- **Comments**: `// line` or `/* block */`.

## Mistakes agents actually make

1. **Missing `required`** — only `id: uuid pk` is implicitly required.
2. **Forgetting `uses entity X`** on a surface.
3. **Enum syntax** — `status: enum[draft, active]`, not `enum(...)`.
4. **Ref syntax** — `owner: ref User`, not `ref(User)`.
5. **String length** — `title: str(200)`, not `str[200]`.
6. **Boolean defaults** — `bool=false`, lowercase.
7. **Scope/permit pairing** — every `scope:` rule needs a matching `permit:` and
   an `as:` clause; a `permit:` without write `scope:` rules makes writes 403 at
   runtime for every role (the project_tracker read-only-app bug, improve cycle 188).
8. **Persona identity in Python** — call `spec_display_id(spec)`
   (`dazzle.core.ir.identity`); never re-inline `getattr(p, "name", ...)`.
   **State names** — call `state_name(s)` / `StateMachineSpec.state_names()`;
   never re-inline `s if isinstance(s, str) else s.name`. Both re-inlines are
   CI-gated (`test_dedup_footgun_gates.py`).

## Where the authoritative lists live (drift-gated — do not copy them here)

- **Constructs**: CLAUDE.md "DSL Quick Reference" — gated by `test_docs_drift.py`.
- **Grammar**: `docs/reference/grammar.md`.
- **Scope-rule forms** (FK paths, EXISTS, poly_ref selectors): CLAUDE.md
  "Scope rules"; verify any scope with `dazzle db explain-scope <Entity> <verb>`.
- **Parser extension checklist**: CLAUDE.md "Extending" (grammar → IR → mixin → tests).
- **Counter-priors** before non-trivial app code: `knowledge counter_prior`.

## Verify

`dazzle validate` after every edit; `dazzle lint` for the extended checks
(RBAC `no_scope_rule` warnings are functional bugs, not style).
