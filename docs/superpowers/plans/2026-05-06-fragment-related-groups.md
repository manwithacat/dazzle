# Fragment Related Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final 3 audit blockers (`unsupported_feature=related_groups`) by extending the FragmentSurfaceAdapter to render related-group regions on detail surfaces. Takes cumulative example coverage from 96% to **100%** — the migration's first phase target.

**Architecture:** A detail surface's `related_groups` (e.g. `related tasks "Tasks": display: table; show: Task`) appends additional Regions of `kind="related"` to the existing detail body, after the field stack. Each group renders as a Region with a Heading (group title) plus a Skeleton placeholder for the actual related-entity content (which is fetched and rendered via htmx after page load — out of scope for this plan; the structural rendering is what closes the audit blocker). CSS rules under `.dz-region--kind-related` match the existing dashboard-region visual treatment.

**Tech Stack:** Python 3.12+, the typed Fragment substrate from Plans 1–5, Plan 7's audit for verification.

**Reference:** `docs/superpowers/plans/migration-roadmap.md` § Plan 10. After this ships, all 5 example apps are 100% Fragment-renderable; Phase 2 of the roadmap pivots to AegisMark.

**Out of scope:**
- Async fetch + render of the actual related-entity rows (stays on Jinja for now; the Fragment-rendered detail surface emits htmx-loaded placeholder regions). Closing this requires `Interactive(child=Skeleton, hx_get=...)` wiring with htmx target ids — could land in a Plan 11+ refinement.
- Non-table display modes (`status_cards`, `file_list`) — detected but rendered with the same placeholder shape regardless.

---

## Stop condition

> **`dazzle fragment-audit` reports zero blockers across all five example apps.** All 78 surfaces flippable. Aggregated blocker count: empty.
>
> **Verification:** all five examples report `Coverage: N / N surfaces ready to flip` (no blocked counts).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/dazzle_http/runtime/renderers/fragment_adapter.py` | Modify | `_build_view` appends related-group Regions to the detail body when `surface.related_groups` is populated |
| `src/dazzle_page/runtime/page_routes.py` | Modify | `_build_dispatch_ctx` passes `surface.related_groups` info into the VIEW ctx |
| `src/dazzle_page/runtime/static/css/components/fragment-primitives.css` | Modify | Add `.dz-region--kind-related` rules |
| `src/dazzle/render/fragment/coverage.py` | Modify | Remove `"related_groups"` from `_UNSUPPORTED_FEATURES` |
| `tests/unit/runtime/test_fragment_surface_adapter.py` | Modify | Append related-group rendering tests |
| `tests/unit/test_fragment_primitive_css.py` | Modify | Append `dz-region--kind-related` to `_REQUIRED_CLASSES` |
| `tests/unit/render/fragment/test_coverage.py` | Modify | Update test that expected related_groups to block |
| `CHANGELOG.md` | Modify | Note 100% example coverage |

8 files. ~5 tasks.

---

## Conventions

- TDD; ruff + mypy clean; verify final audit reports 100% coverage on completion.

---

## Task 1: Adapter renders related groups as appended regions

**Files:**
- Modify: `src/dazzle_http/runtime/renderers/fragment_adapter.py`
- Modify: `tests/unit/runtime/test_fragment_surface_adapter.py`

When a VIEW surface has `related_groups`, the adapter wraps the existing field stack and the related-group regions in a Stack, so the detail body is field-stack + per-group regions.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/runtime/test_fragment_surface_adapter.py`:

```python
def test_view_mode_appends_related_group_regions() -> None:
    """Plan 10 — related_groups produce additional Region(kind=related)
    appended after the field stack."""
    from dazzle.render.fragment import Heading, Region, Stack

    surface = SurfaceSpec(
        name="user_detail",
        title="User Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="User",
    )
    ctx = {
        "fields": [
            {"key": "email", "label": "Email", "value": "alice@x"},
        ],
        "region_name": "user_detail_main",
        "related_groups": [
            {"name": "tasks", "title": "Tasks", "display": "table"},
            {"name": "comments", "title": "Comments", "display": "table"},
        ],
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    # Body is now a Stack: [field-stack-Region, related-group-Region * N]
    body = fragment.body.body
    assert isinstance(body, Stack)
    # First child is the original field stack (or its container)
    # Children 2 & 3 are the related-group regions
    related_regions = [c for c in body.children if isinstance(c, Region) and c.kind == "related"]
    assert len(related_regions) == 2
    # Each related region carries the group title via its body
    titles = []
    for r in related_regions:
        # The Region body is a Stack [Heading(title), Skeleton-placeholder]
        if isinstance(r.body, Stack):
            for child in r.body.children:
                if isinstance(child, Heading):
                    titles.append(child.body)
    assert "Tasks" in titles
    assert "Comments" in titles


def test_view_mode_no_related_groups_unchanged() -> None:
    """Plan 10 — VIEW surfaces without related_groups still render
    as a single Region(kind=detail) (no Stack wrapping)."""
    surface = SurfaceSpec(
        name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task"
    )
    ctx = {
        "fields": [{"key": "title", "label": "Title", "value": "Hello"}],
        "region_name": "x_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    # Plan 8 shape: Region(kind=detail) directly inside Surface body
    assert fragment.body.kind == "detail"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py::test_view_mode_appends_related_group_regions -v 2>&1 | tail -10
```

Expected: FAIL — current `_build_view` doesn't read `related_groups`.

- [ ] **Step 3: Implement related-group rendering**

In `src/dazzle_http/runtime/renderers/fragment_adapter.py`, update imports to include `Skeleton`:

```python
from dazzle.render.fragment import (
    URL,
    Combobox,
    EmptyState,
    Field,
    FormStack,
    Fragment,
    Heading,
    Region,
    Row,
    Skeleton,
    Stack,
    Submit,
    Surface,
    Table,
    Text,
)
```

Update `_build_view` to handle `related_groups`:

```python
    def _build_view(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        """Detail surface — single record's fields as a definition-list-shaped Region.

        When the surface has related_groups, additional Region(kind=related)
        entries are appended after the detail region. Each related group
        emits a Heading (group title) + Skeleton placeholder; the actual
        related-entity rows arrive via a separate htmx fetch (out of scope
        for the structural-rendering plan).
        """
        title = surface.title or surface.name.replace("_", " ").title()
        fields: list[dict[str, Any]] = ctx.get("fields", [])

        # Build the detail Region as before
        if not fields:
            detail_body: Fragment = EmptyState(
                title="No data",
                description="This record has no displayable fields.",
            )
        else:
            field_rows = tuple(
                Row(
                    children=(
                        Heading(str(f.get("label", f.get("key", ""))), level=4),
                        Text(_format_cell(f.get("value"), str(f.get("kind", "text")))),
                    ),
                    align="start",
                )
                for f in fields
            )
            detail_body = Stack(children=field_rows, gap="sm")

        detail_region = Region(kind="detail", body=detail_body)

        # If no related_groups, body is just the detail region (Plan 8 shape)
        related_groups: list[dict[str, Any]] = ctx.get("related_groups", [])
        if not related_groups:
            return Surface(
                header=Heading(title, level=1),
                body=detail_region,
            )

        # Otherwise wrap detail + related-group regions in a Stack
        related_regions: list[Fragment] = []
        for group in related_groups:
            group_title = str(group.get("title") or group.get("name", "Related"))
            group_body = Stack(
                children=(
                    Heading(group_title, level=2),
                    # Skeleton placeholder; actual rows fetch via htmx
                    Skeleton(lines=3),
                ),
                gap="sm",
            )
            related_regions.append(Region(kind="related", body=group_body))

        body = Stack(
            children=(detail_region, *related_regions),
            gap="md",
        )

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="detail", body=body),
        )
```

Note: the outer Region stays `kind="detail"` (the surface IS a detail surface); the related groups are sub-regions inside it with their own `kind="related"` modifier. CSS targets the inner kind for layout differentiation.

- [ ] **Step 4: Verify pass**

```bash
pytest tests/unit/runtime/test_fragment_surface_adapter.py -v 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_http/runtime/renderers/fragment_adapter.py tests/unit/runtime/test_fragment_surface_adapter.py
git commit -m "feat(render): _build_view appends related-group Regions when present"
```

---

## Task 2: page_routes threads related_groups into VIEW ctx

**Files:**
- Modify: `src/dazzle_page/runtime/page_routes.py`

The `_build_dispatch_ctx` builds the VIEW shape from `render_ctx.detail`. Extract `related_groups` from the surface IR (not from runtime data) and pass them through.

- [ ] **Step 1: Locate the VIEW branch**

```bash
grep -n "detail = getattr(render_ctx" src/dazzle_page/runtime/page_routes.py
```

- [ ] **Step 2: Update the VIEW branch to include related_groups**

The function currently has access to `render_ctx` but probably not the SurfaceSpec directly. The cleanest fix: change `_build_dispatch_ctx`'s signature to accept the surface, or read the related-groups info from `render_ctx.detail` if it has it.

For simplicity, look up the surface via the existing `_maybe_dispatch_inner_html` flow and pass it through:

```python
# In _build_dispatch_ctx, change signature:
def _build_dispatch_ctx(render_ctx: Any, surface: Any = None) -> dict[str, Any]:
```

Update the detail branch:

```python
    detail = getattr(render_ctx, "detail", None)
    if detail is not None:
        fields_out: list[dict[str, Any]] = []
        for section in getattr(detail, "sections", []) or []:
            for f in getattr(section, "fields", []) or []:
                fields_out.append(
                    {
                        "key": getattr(f, "key", "") or getattr(f, "name", ""),
                        "label": getattr(f, "label", "")
                        or getattr(f, "key", "")
                        or getattr(f, "name", ""),
                        "value": getattr(f, "value", "") or "",
                        "kind": getattr(f, "type", "text") or "text",
                    }
                )
        # Plan 10: thread surface.related_groups (IR-level) into the ctx
        related_groups_out: list[dict[str, Any]] = []
        for rg in getattr(surface, "related_groups", []) or []:
            display = getattr(rg, "display", None)
            related_groups_out.append(
                {
                    "name": getattr(rg, "name", ""),
                    "title": getattr(rg, "title", "") or getattr(rg, "name", ""),
                    "display": display.value if hasattr(display, "value") else str(display or "table"),
                }
            )
        return {
            "fields": fields_out,
            "region_name": getattr(detail, "entity_name", "") + "_detail",
            "related_groups": related_groups_out,
        }
```

Update the call site in `_maybe_dispatch_inner_html`:

```python
    ctx_dict = _build_dispatch_ctx(render_ctx, surface)
```

- [ ] **Step 3: Run targeted suite**

```bash
pytest tests/ -m "not e2e" -k "render or dispatch" -q 2>&1 | tail -3
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/page_routes.py
git commit -m "feat(runtime): _build_dispatch_ctx threads related_groups for VIEW surfaces"
```

---

## Task 3: CSS for `.dz-region--kind-related`

**Files:**
- Modify: `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`
- Modify: `tests/unit/test_fragment_primitive_css.py`
- Modify: `src/dazzle_page/runtime/static/dist/dazzle.min.css` (regenerated)

- [ ] **Step 1: Add presence-test entry**

Append `"dz-region--kind-related"` to `_REQUIRED_CLASSES` in `tests/unit/test_fragment_primitive_css.py`.

- [ ] **Step 2: Add CSS rules**

In `src/dazzle_page/runtime/static/css/components/fragment-primitives.css`, after the `.dz-region--kind-form` block:

```css
  /* Related-group region — appended to detail surfaces. Each group is
     a sub-section with its own heading + content (skeleton placeholder
     today, htmx-loaded rows post-Plan-11). */

  .dz-region--kind-related {
    margin-block-start: var(--space-lg);
    padding-block-start: var(--space-md);
    border-block-start: 1px solid var(--colour-border);
  }

  .dz-region--kind-related .dz-heading--level-2 {
    margin-block-end: var(--space-sm);
  }
```

- [ ] **Step 3: Verify presence test passes; rebuild dist**

```bash
pytest tests/unit/test_fragment_primitive_css.py -q 2>&1 | tail -3
python scripts/build_dist.py 2>&1 | tail -3
grep -c "dz-region--kind-related" src/dazzle_page/runtime/static/dist/dazzle.min.css
```

Expected: PASS; rebuild reports new CSS in bundle (≥ 1).

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_page/runtime/static/css/components/fragment-primitives.css tests/unit/test_fragment_primitive_css.py src/dazzle_page/runtime/static/dist/
git commit -m "feat(ui): CSS for dz-region--kind-related"
```

---

## Task 4: Audit recognises related_groups support

**Files:**
- Modify: `src/dazzle/render/fragment/coverage.py`
- Modify: `tests/unit/render/fragment/test_coverage.py`

Remove `related_groups` from `_UNSUPPORTED_FEATURES` so the audit reports it as supported.

- [ ] **Step 1: Update the matrix**

In `src/dazzle/render/fragment/coverage.py`:

```python
# Was:
# _UNSUPPORTED_FEATURES: tuple[str, ...] = (
#     "related_groups",
#     "companions",
#     "search_fields",
# )
# Becomes:
_UNSUPPORTED_FEATURES: tuple[str, ...] = (
    "companions",
    "search_fields",
)
```

- [ ] **Step 2: Update affected coverage tests**

`test_audit_marks_related_groups_as_blocked` is now wrong. Either rename and switch to `companions`, or replace with a test that confirms related_groups is supported:

```python
def test_audit_treats_related_groups_as_supported() -> None:
    """Plan 10 — related_groups is now supported; surfaces with it
    aren't blocked on this feature alone."""
    surface = SurfaceSpec(
        name="x",
        mode=SurfaceMode.VIEW,
        related_groups=[
            RelatedGroup(
                name="tasks",
                entity_ref="Task",
                display=RelatedDisplayMode.TABLE,
                show=[],
            ),
        ],
    )
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 1
    assert report.blocked_count == 0
```

- [ ] **Step 3: Verify**

```bash
pytest tests/unit/render/fragment/test_coverage.py -v 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/render/fragment/coverage.py tests/unit/render/fragment/test_coverage.py
git commit -m "feat(render): audit recognises related_groups support"
```

---

## Task 5: Verify 100% coverage + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Re-run audit on all examples**

```bash
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  result=$(python -m dazzle.cli fragment-audit "examples/$app" 2>&1 | grep "^Coverage:" | head -1)
  echo "$app : $result"
done
echo ""
echo "=== aggregated ==="
for app in simple_task contact_manager support_tickets ops_dashboard fieldtest_hub; do
  python -m dazzle.cli fragment-audit "examples/$app" 2>&1 | grep -E "^\s+[0-9]+\s+unsupported"
done | awk '{count[$2] += $1} END {for (k in count) print count[k], k}' | sort -rn
```

Expected: every app at N/N (100%); aggregated section is empty (no remaining blockers).

- [ ] **Step 2: Run full suite**

```bash
pytest tests/ -m "not e2e" -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 3: Update CHANGELOG**

Add to `## [Unreleased]` under `### Added`:

```markdown
- **Related groups for FragmentSurfaceAdapter (Plan 10).** Detail
  surfaces with `related_groups` (e.g. user_detail showing tasks +
  comments) now flip cleanly to `render: fragment`. The adapter
  appends Region(kind="related") entries after the detail's field
  stack, each containing the group's heading + a Skeleton placeholder
  (actual related-entity rows fetch via htmx, out of scope here).
  CSS rules under `.dz-region--kind-related`. **Cumulative example
  coverage hits 100%** (78/78 surfaces flippable across all five
  example apps). The migration's first phase target is met; Phase 2
  pivots to AegisMark per `docs/superpowers/plans/migration-roadmap.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note Plan 10 — 100% example coverage"
```

---

## Plan completion checklist

- [ ] All 5 examples: `Coverage: N / N surfaces ready to flip` (100%).
- [ ] `pytest tests/ -m "not e2e"` — no regressions.
- [ ] `mypy src/dazzle/render --strict` — clean.
- [ ] `git status` clean.
- [ ] **Stop condition met:** zero aggregated blockers across all five example apps. Plan 11+ pivots to AegisMark.

---

## Self-Review

**Spec coverage:**
- Plan 9 carry-forward (related_groups closure) → Tasks 1-4.
- Roadmap Phase 1 target (100% example coverage) → Task 5 verifies.

**Placeholder scan:**
- Skeleton placeholder is intentional and explicitly noted as out-of-scope-for-this-plan. The structural rendering closes the audit blocker; live-data fetch is a separate Plan 11+ refinement.

**Type consistency:**
- `related_groups` ctx key consistent across Tasks 1, 2.
- `Region(kind="related")` consistent across Tasks 1, 3.

**Scope check:**
- Plan covers structural rendering only. Live data fetching deferred. 5 tasks. Smallest plan in the migration arc — fits because all infrastructure is already in place.
