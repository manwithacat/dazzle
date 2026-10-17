---
name: dsl-authoring
description: Use when writing or editing Dazzle .dsl files — syntax rules, the mistakes agents actually make, and pointers to the drift-gated references. Complements (never replaces) AGENTS.md's DSL Quick Reference.
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
9. **Action visibility vs. permission (#1787)** — a surface `action` takes an
   optional `visible:` line (same grammar as field `visible:`, either order with
   the `on` line):
   ```dsl
   action send_letter "Send the request letter":
     visible: status = draft and (role(agent) or role(manager))
     on click -> "/information-requests/{id}/letter" external
   ```
   It hides the action per record. Only `integration X action Y` outcomes are
   also refused on POST; external/surface/experience targets must check
   permission themselves. Do not write `on click -> transition …` (no such
   outcome, DD-016): gate state changes with `role(...)` on the entity's
   `transitions:` — those guards now also decide which transition buttons render.

## Where the authoritative lists live (drift-gated — do not copy them here)

- **Constructs**: AGENTS.md "DSL Quick Reference" — gated by `test_docs_drift.py`.
- **Grammar**: `docs/reference/grammar.md`.
- **Scope-rule forms**: the section below (moved here from AGENTS.md); runtime
  semantics in `docs/reference/rbac-scope.md`; verify any scope with
  `dazzle db explain-scope <Entity> <verb>`.
- **Parser extension checklist**: AGENTS.md "Extending" (grammar → IR → mixin → tests).
- **Counter-priors** before non-trivial app code: `knowledge counter_prior`.

## Scope-rule forms

Scope rules compile to a formal predicate algebra and are statically validated
against the FK graph at `dazzle validate` time. Supported forms:

- Direct: `school_id = current_user.school` — column equality check
- FK path (depth-N): `manuscript.assessment_event.school_id = current_user.school` — nested subquery
- EXISTS: `via JunctionEntity(field = current_user.attr, field = id)` — junction table check
- NOT EXISTS: `not via BlockList(user = current_user, resource = id)` — negated junction check
- Negation: `not (status = archived)` — parenthesised negation
- Boolean: `realm = current_user.realm or creator = current_user` — AND/OR compile to SQL
- Polymorphic ref (#1448/#1455): `subject[CohortAssessment].uploaded_by = current_user` —
  for a typed `poly_ref subject [CohortAssessment, Manuscript]` field (two columns
  `subject_type text` + `subject_id uuid`, targets uuid-pk). `[Type]` selects the branch,
  then a normal path/expression on that target. A bare `subject.x` (no selector) is a
  validation error (`E_POLY_SELECTOR_REQUIRED`). Multi-branch = repeated rules. Supported
  on all verbs (read/list/delete + create/update via the payload-time probe, #1455).

Use `revoked_at = null` for literal null filters, `!=` for not-equals. Each `scope:`
rule needs a matching `permit:` rule and an `as:` clause naming the personas (`as:`
replaced the overloaded `for:` keyword in #998).

## Verify

`dazzle validate` after every edit; `dazzle lint` for the extended checks
(RBAC `no_scope_rule` warnings are functional bugs, not style).
