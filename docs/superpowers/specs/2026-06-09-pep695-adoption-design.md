# PEP 695 Adoption — Design

**Date:** 2026-06-09 · **Status:** approved, pre-implementation
**Floor:** unchanged (`requires-python = ">=3.12"`). **This is NOT the floor move.**

---

## 1. Objective & scope

Adopt PEP 695 native type-parameter syntax (`class C[T]`, `def fn[T]()`, `type X = …`) across the
**18 sites currently deferred** via the `UP040/UP046/UP047` ruff ignores (`pyproject.toml`, the #1175 note),
and remove those three ignores so the modernization is enforced going forward.

**Why now, and why decoupled from the floor move:** PEP 695 syntax has been legal since Python 3.12, so it
needs no floor change — the deferral was a deliberate "reviewed refactor, not a metadata side effect" gate,
not a version constraint. During floor-move planning we established that the floor move's *unique* payoff (the
`from __future__ import annotations` cleanup) requires a 3.14 floor (PEP 649), whereas PEP 695 does not — so we
take the floor-independent modernization now and leave the floor decision deferred. The floor stays `>=3.12`;
full 3.12 / 3.13 / 3.14 support is retained.

## 2. The 18 sites (all in `src/`, none in tests)

| File | Construct(s) | Rule |
|---|---|---|
| `back/events/service_mixin.py` | `EventEmittingMixin`, `EventEmittingCRUDService` | UP046 ×2 |
| `back/graphql/adapters/base.py` | `AdapterResponse`, `PaginatedResponse`, `AdapterResult`, `BaseExternalAdapter` | UP046 ×4 |
| `back/runtime/repository.py` | `Repository` (class); `DatabaseManager` (2 type aliases) | UP046 ×1, UP040 ×2 |
| `back/runtime/service_generator.py` | `BaseService`, `CRUDService` | UP046 ×2 |
| `cli_ui.py` | `SelectOption` (class); `select_interactive`, `_select_with_keyboard`, `_select_simple` (fns) | UP046 ×1, UP047 ×3 |
| `mcp/server/handlers/common.py` | `run_with_timeout` (fn) | UP047 ×1 |
| `result.py` | `Ok`, `Err` | UP046 ×2 |

Totals: **12 generic classes, 4 generic functions, 2 type aliases.**

## 3. Risk analysis & per-site review checklist

ruff classifies these as **unsafe** fixes because PEP 695 changes type-parameter *scoping*. Assessed against the
affected modules:

1. **Explicit variance — ABSENT (highest risk, not present).** No `covariant=`/`contravariant=` TypeVars exist
   in any affected module (verified). PEP 695 infers variance, so this would have been the one case that
   silently changes semantics — it does not arise here.
2. **Bounds — PRESENT, handled.** The TypeVars carry `bound=` (`BaseModel`, `AdapterConfig`, `type`,
   `enum.Enum`). These convert to `class C[T: Bound]`; verify ruff carried each bound across correctly.
3. **Shared module-level TypeVars — the real review.** Paired classes share module TypeVars:
   `service_mixin.py` (`T`/`CreateT`/`UpdateT` across both classes), `service_generator.py` (same),
   `result.py` (`Ok`/`Err`). After conversion each class gets its own scoped param; the module-level TypeVar is
   then **dead iff no non-converted consumer uses it**. Review action per module: confirm the module TypeVar is
   used *only* by the converted classes, then **remove it**; if a function/standalone annotation also uses it,
   **keep it** (and that signature stays on the classic TypeVar).
4. **`type` statement is lazy (UP040 only).** `X: TypeAlias = V` → `type X = V` produces a `TypeAliasType`
   object, not `V`. Confirm `DatabaseManager` is used only in annotations, never at runtime (no
   `isinstance(_, DatabaseManager)`, no use as a real value). If it's used as a value, leave it as `TypeAlias`.

**Safety net:** mypy 2.1.0 (full PEP 695 support) + the full 17,887-test suite + the api-surface drift gate
(`ir-types.txt` renders annotations — watch for diffs) catch scoping/variance/repr regressions. Strong, but
each of the 12 class sites still gets manual eyes for items 2–3 above; the autofixer is the starting point, not
the verdict.

## 4. Approach

1. `ruff check src/ --select UP040,UP046,UP047 --fix --unsafe-fixes` — mechanical conversion of all 18 sites.
2. Manual review pass over the 12 class sites + 2 aliases for §3 items 2–4; remove now-dead module TypeVars;
   `ruff format`.
3. Remove the `UP040`, `UP046`, `UP047` entries (and the #1175 deferral comment) from `pyproject.toml`'s
   `[tool.ruff.lint] ignore`, so the syntax is enforced going forward.
4. Verify (gates in §5). One slice, one release.

*Alternatives considered & rejected:* (a) fully manual conversion — no safety gain over autofix-then-review for
18 sites; (b) staging UP040/UP047 first, deferring UP046 — unnecessary, the 12 class sites are reviewable in one
pass and share no cross-file state.

## 5. Verification gates

- `ruff check src/ tests/` clean **with the three ignores removed** (proves no remaining non-PEP-695 generics
  and that the conversions satisfy the now-active rules).
- `ruff format --check` clean.
- `mypy src/dazzle` clean (the primary scoping/variance check).
- Full unit suite `pytest -m "not e2e"` green on the **3.12 floor** (PEP 695 is identical across 3.12–3.14, so
  floor-green ⟹ matrix-green; the CI matrix confirms on 3.13/3.14).
- Drift/policy gates green, incl. `test_api_surface_drift` (`ir-types.txt` unchanged or regenerated with a
  CHANGELOG note).
- CHANGELOG entry under Changed; `/bump` + `uv lock` per the established release flow.

## 6. Out of scope (explicitly deferred)

- **The floor move** (`>=3.13`/`>=3.14`) — separate product decision; unchanged by this work.
- **`from __future__ import annotations` cleanup** (669 files) — gated on a 3.14 floor (PEP 649) + ADR-0014;
  not touched here.
- **`tests/`** — 0 PEP 695 sites; nothing to do.

## 7. Rollout

Single slice → single patch release. No API-surface change expected (internal generics); if the api-surface
baseline shifts, regenerate with `--write` + CHANGELOG note. Floor, deploy targets, and CI matrix unchanged.
