# Auth↔domain-`User` bridge (#778 / #1398) — Implementation Plan

> **For agentic workers:** execute task-by-task under the **phase-contract** skill. Steps use `- [ ]`.

**Goal:** Implement ADR-0039 — a declared, validated `auth_identity:` binding on the `User`
entity that (a) provisions the domain `User` row on real auth-user creation and (b) injects the
domain row's id (resolved by `link_via`) into `ref User` FKs — closing #778/#1398 without touching
`session.user_id` (D1).

**Architecture:** New `AuthIdentitySpec` on `EntitySpec` (D2). Validate-time completeness check
(D6/A1). A path-neutral `mirror_auth_user_to_domain(...)` helper (D4) called from the test route
**and** the production `auth_store.create_user` choke point (D3a). `link_via` resolution replaces
the `target == "User"` auth-id special-case in `route_generator` **only when a binding is declared**
(D3b/D5). Undeclared `User` behaves exactly as today (D5/D7).

**Tech Stack:** Python 3.12, frozen dataclasses (IR), the existing lexer/parser-mixin pattern,
psycopg3 (`deps.db_manager.connection()`), pytest.

## Global Constraints (verbatim from ADR-0039 / CLAUDE.md)
- **D1 — never repoint `session.user_id`.** No change to `SessionRecord`, `create_session`,
  membership, RLS, or audit.
- **D5/D7 — opt-in.** No `auth_identity:` ⇒ behaviour identical to today (auth-id injection, no mirror).
- **A1 — fail at validate, never swallow at runtime.** An `auth_identity:` that doesn't resolve every
  required-no-default column on `User`, or binds an RLS-fenced `User`, is a **validate-time error**.
- Bind **at most one** entity. v1 link field: `email` only (validated/tested).
- Ship discipline: per-phase gate green → `/bump patch` + commit + push (batch full suite + push at
  each SLICE boundary). `pytest -m "not e2e"`, `ruff check`, `mypy src/dazzle`, drift baselines.

---

## File map
- `src/dazzle/core/ir/domain.py` — `AuthIdentitySpec`; `EntitySpec.auth_identity: AuthIdentitySpec | None = None`.
- `src/dazzle/core/lexer.py` — `AUTH_IDENTITY = "auth_identity"` TokenType.
- `src/dazzle/core/dsl_parser_impl/entity.py` — `_parse_entity_auth_identity()` + dispatch arm + ctx field.
- `src/dazzle/core/validation/entities.py` — `validate_auth_identity_binding(appspec)`.
- `src/dazzle/back/runtime/auth_identity_mirror.py` (new) — `mirror_auth_user_to_domain(deps, identity, binding)`.
- `src/dazzle/back/runtime/test_routes.py` — call the shared helper (delete the divergent copy).
- `src/dazzle/back/runtime/auth/store.py` — production mirror hook in/after `create_user`.
- `src/dazzle/back/runtime/route_generator.py` (~L561) — `link_via` resolution for declared-binding `ref User`.

---

## SLICE 1 — IR + parser for `auth_identity:` (D2)

### Task 1.1: `AuthIdentitySpec` IR + EntitySpec field
- [ ] Add frozen dataclass to `core/ir/domain.py`:
```python
@dataclass(frozen=True)
class AuthIdentitySpec:
    """ADR-0039: declares this entity is the auth principal's domain projection.

    link_via   — column joining the domain row to the auth identity (v1: "email").
    field_map  — (domain_col, source) where source ∈ {id,email,email_localpart,username,role}.
    defaults   — (domain_col, literal) NOT-NULL columns the auth flow can't supply.
    """
    link_via: str = "email"
    field_map: tuple[tuple[str, str], ...] = ()
    defaults: tuple[tuple[str, str], ...] = ()
```
- [ ] Add `auth_identity: AuthIdentitySpec | None = None` to `EntitySpec`.
- [ ] Export `AuthIdentitySpec` from `core/ir/__init__.py` `__all__`.
- [ ] Gate: `dazzle inspect api ir-types --write` regen + drift green; ruff + mypy.

### Task 1.2: lexer token + parser block + dispatch
- [ ] `AUTH_IDENTITY = "auth_identity"` in lexer (mirror `EXPOSE` at L199); register the keyword.
- [ ] `_parse_entity_auth_identity()` in `entity.py` (precedent: `_parse_entity_expose` L251):
  parses `link_via: <ident>` (default email), `map:` `{ col: source, ... }`, `default:`
  `{ col: <literal>, ... }`. Unknown source token / op = parse error.
- [ ] Dispatch arm: `elif self.match(TokenType.AUTH_IDENTITY): ctx.auth_identity = self._parse_entity_auth_identity()` (after EXPOSE, L201); add `auth_identity` to `_EntityParseContext` + `_build_entity_spec`.
- [ ] **TDD gate:** `tests/unit/test_auth_identity_parsing.py` — round-trips a `User` with
  `auth_identity: link_via: email / map: {username: email_localpart}` into `EntitySpec.auth_identity`;
  rejects an unknown `map` source. ruff + mypy + golden-master regen if needed.

**SLICE 1 boundary:** full `pytest -m "not e2e"` + `/bump` + commit + push.

---

## SLICE 2 — validate-time completeness (D6/A1)

### Task 2.1: `validate_auth_identity_binding`
- [ ] In `core/validation/entities.py`: for each entity with `auth_identity`:
  - error if more than one entity declares it (bind at most one);
  - error if `link_via` is not a column on the entity;
  - error if `link_via != "email"` (v1 scope);
  - error if any **required, no-default** column is not covered by `field_map`/`defaults`
    (the #1398/#778 swallow-failure → static error);
  - error if the entity is RLS-fenced/tenanted (has a `tenant_id`/membership fence) — reject with a
    message directing the author to make `User` global (D6).
- [ ] Wire into the validation pass that `dazzle validate` runs.
- [ ] **TDD gate:** `tests/unit/test_auth_identity_validation.py` — (a) unresolved required column →
  ValidationError; (b) `link_via` not a column → error; (c) two bindings → error; (d) a fully-resolved
  global `User` → clean. ruff + mypy.

**SLICE 2 boundary:** full `pytest -m "not e2e"` + `/bump` + commit + push.

---

## SLICE 3 — shared mirror helper + production hook (D3a/D4)

### Task 3.1: extract path-neutral helper
- [ ] New `back/runtime/auth_identity_mirror.py`: `mirror_auth_user_to_domain(deps, *, user_id, email,
  username, role, binding)`. When `binding` is present, resolve each domain column from
  `field_map`/`defaults` (sources: id→user_id, email→email, email_localpart→email.split('@')[0],
  username→username, role→role) — the **declared** map, not placeholder heuristics. Idempotent
  `INSERT ... ON CONFLICT (link_via col) DO UPDATE`. When `binding is None`, fall back to the existing
  schema-derived best-effort (preserve today's test-route behaviour for undeclared `User`).
- [ ] `test_routes.py`: replace the in-file `_mirror_auth_user_to_domain` body with a call to the
  shared helper (pass the entity's `auth_identity` binding, or None).
- [ ] **TDD gate:** `tests/unit/test_auth_identity_mirror.py` — declared binding produces the upsert
  SQL covering exactly the mapped+default+link columns; conflict target is `link_via`. ruff + mypy.

### Task 3.2: production hook at `create_user`
- [ ] Call the shared helper from the production auth-user choke point so magic-link signup, SSO JIT
  (`enterprise_login.create_user`), and password signup all mirror the domain `User` when a binding is
  declared. Guard on binding-present; no-op when absent (D5). No change to `create_user`'s return /
  session semantics (D1).
- [ ] **TDD gate:** `tests/unit/test_auth_identity_production_mirror.py` — a declared-binding app:
  creating an auth user provisions the matching domain `User` row (link_via=email); an undeclared app:
  no mirror. ruff + mypy.

**SLICE 3 boundary:** full `pytest -m "not e2e"` + (DB suite if touched) + `/bump` + commit + push.

---

## SLICE 4 — `link_via` injection for declared `ref User` (D3b/D5)

### Task 4.1: resolve domain id by link, when declared
- [ ] In `route_generator.py` (~L561): when the target `User` entity declares `auth_identity`, route
  the `ref User` field through the **same `persona_ref_map` link-resolution** used for backed entities
  (resolve the domain `User` row by `link_via == current_user.email`, inject **its** id) instead of the
  `user_ref_fields` auth-id injection. When `User` has **no** binding, keep the current `#774` auth-id
  injection unchanged (D5).
- [ ] **TDD gate:** `tests/unit/test_auth_identity_injection.py` — declared binding ⇒ `ref User` field
  is in the link-resolved map (not the raw auth-id `user_ref_fields` set); undeclared ⇒ unchanged. ruff + mypy.

### Task 4.2: end-to-end example + close-out
- [ ] Add the `auth_identity:` declaration to one example whose `User` uses non-`name` columns (or a
  fixture) so the bridge is dogfooded; ensure RBAC-lint + matrix-completeness gates stay green.
- [ ] Update `CLAUDE.md` DSL reference (add `auth_identity` to the entity-block list) + ADR-0039 status
  → implemented; counter-prior/docs if warranted.
- [ ] Mark ADR-0039 implemented; post #778 + #1398 close-out comments (`🔖 Claude-lens: dazzle`).

**SLICE 4 / completion:** full gate end-to-end (`ruff && mypy && pytest -m "not e2e"`) + drift +
`mkdocs build --strict` + `/bump` + commit + push.
