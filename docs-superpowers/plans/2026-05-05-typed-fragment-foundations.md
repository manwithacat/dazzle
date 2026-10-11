# Typed Fragment Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed Fragment library — frozen-dataclass primitives, render context, token system, htmx field types, primitive registry, and an HTML-emitting renderer — entirely in isolation from Dazzle's serving path. By the end of this plan, you can construct any framework primitive in Python and render it to a valid HTML5 string, but no DSL surface has been flipped and no template has been replaced.

**Architecture:** A new `src/dazzle/render/` package with a `fragment/` subpackage. Frozen dataclasses for primitives with `__post_init__` invariants. Match-dispatch renderer over a discriminated union. Tokens flow through a `RenderContext`. ID and CSS class derivation centralised in shared helpers (`ids.py`, `classes.py`) so a future Jinja-side integration can read from the same source of truth. No changes to existing serving code; the package is import-only.

**Tech Stack:** Python 3.12+, `@dataclass(frozen=True, slots=True)`, mypy, pytest. No new third-party dependencies.

**Reference spec:** [`docs/superpowers/specs/2026-05-05-typed-fragment-emitter-design.md`](../specs/2026-05-05-typed-fragment-emitter-design.md). Phases 0–3 of that spec.

**Out of scope for this plan:** the `render:` DSL clause, IR field additions, `RuntimeServices` registry wiring, parity tests against existing Jinja templates, scanner retirement, any flip of an example app. Those are Plans 2 and 3.

---

## File Structure

```
src/dazzle/render/
├── __init__.py                 # package marker; no public exports
├── ids.py                      # id_for(ir_node) helper — single source of truth for element ids
├── classes.py                  # classes_for(ir_node, tokens) — single source of truth for CSS classes
└── fragment/
    ├── __init__.py             # public exports (Fragment, primitive types, renderer)
    ├── tokens.py               # CardTokens, ButtonTokens, ..., Tokens
    ├── context.py              # RenderContext (carries tokens + helpers during render)
    ├── errors.py               # FragmentError, CardSafetyError, HtmxBindingError
    ├── htmx.py                 # URL, TargetSelector, HxTrigger wrapper types
    ├── escape.py               # RawHTML, Slot — escape-hatch primitives
    ├── registry.py             # PrimitiveRegistry + @primitive decorator
    ├── primitives/
    │   ├── __init__.py
    │   ├── _base.py            # Fragment type alias = Card | Region | ... | RawHTML | Slot
    │   ├── layout.py           # Stack, Row, Split, Grid
    │   ├── containers.py       # Surface, Card, Region, Toolbar, Drawer, Modal, Tabs
    │   ├── content.py          # Text, Heading, Icon, Badge, EmptyState, Skeleton
    │   ├── interactive.py      # Button, Link, InlineEdit, Interactive
    │   ├── data.py             # Table, KanbanBoard, CalendarGrid, Timeline, KPI, BarChart, PivotTable
    │   └── forms.py            # FormStack, Field, Combobox, Submit
    └── renderer.py             # FragmentRenderer with match-dispatch

tests/unit/render/
├── __init__.py
├── test_ids.py
├── test_classes.py
└── fragment/
    ├── __init__.py
    ├── test_tokens.py
    ├── test_htmx_types.py
    ├── test_layout_primitives.py
    ├── test_container_primitives.py     # the load-bearing invariant tests live here
    ├── test_content_primitives.py
    ├── test_interactive_primitives.py
    ├── test_data_primitives.py
    ├── test_form_primitives.py
    ├── test_escape_primitives.py
    ├── test_registry.py
    ├── test_renderer_layout.py
    ├── test_renderer_containers.py
    ├── test_renderer_interactive.py
    ├── test_renderer_data.py
    ├── test_renderer_forms.py
    ├── test_html5_validity.py            # property-style: every primitive emits valid HTML5
    └── test_fragment_exhaustiveness.py   # every member of Fragment union is renderable
```

23 source files, 18 test files. Each source file has one clear responsibility; each test file pins behaviour for one source file (or one primitive cluster).

**Boundary discipline:** nothing in this package imports from `src/dazzle_http/`, `src/dazzle_page/`, or `src/dazzle/core/ir/`. The package takes IR-shaped inputs as plain dataclass arguments at the boundary (the renderer's input is a `Fragment`, not an `AppSpec`). This isolation is what makes Plan 2's integration cheap.

---

## Conventions used in every task

- **TDD throughout.** Every task writes a failing test first, runs it to confirm failure, implements minimally, runs to confirm pass, commits.
- **Test command:** `pytest tests/unit/render/<path> -v`. Use `-x` to stop on first failure during local iteration.
- **Lint after each task:** `ruff check src/dazzle/render tests/unit/render --fix && ruff format src/dazzle/render tests/unit/render`.
- **Type check after each task:** `mypy src/dazzle/render --strict`. New code must pass strict mode; this is the substrate that enforces the invariants, so weak typing here defeats the design.
- **Commit messages:** `feat(render): <task subject>` for source additions; `test(render): <task subject>` for test-only additions; `chore(render): <task subject>` for scaffolding.
- **No `from __future__ import annotations` in this package.** The match-dispatch in the renderer (Task 21+) needs runtime type information; future-annotations breaks it. Pin this in `src/dazzle/render/__init__.py` with a comment.

---

## Phase 0 — Foundations

### Task 1: Create render package skeleton

**Files:**
- Create: `src/dazzle/render/__init__.py`
- Create: `src/dazzle/render/fragment/__init__.py`
- Create: `src/dazzle/render/fragment/primitives/__init__.py`
- Create: `tests/unit/render/__init__.py`
- Create: `tests/unit/render/fragment/__init__.py`
- Create: `tests/unit/render/fragment/test_package_imports.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/render/fragment/test_package_imports.py
def test_render_package_importable() -> None:
    import dazzle.render
    import dazzle.render.fragment
    import dazzle.render.fragment.primitives
    assert dazzle.render.__name__ == "dazzle.render"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/render/fragment/test_package_imports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.render'`

- [ ] **Step 3: Create the package files**

```python
# src/dazzle/render/__init__.py
"""Render layer — IR-driven HTML emission via typed Fragments.

This package does NOT use `from __future__ import annotations`. The match-
dispatch in `fragment.renderer` requires runtime type information.
"""
```

```python
# src/dazzle/render/fragment/__init__.py
"""Typed Fragment system — frozen-dataclass primitives + HTML renderer."""
```

```python
# src/dazzle/render/fragment/primitives/__init__.py
"""Framework primitive types organised by category."""
```

```python
# tests/unit/render/__init__.py
# (empty)
```

```python
# tests/unit/render/fragment/__init__.py
# (empty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/render/fragment/test_package_imports.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render tests/unit/render
git commit -m "chore(render): create render and fragment package skeletons"
```

---

### Task 2: ID derivation helper

**Files:**
- Create: `src/dazzle/render/ids.py`
- Create: `tests/unit/render/test_ids.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/test_ids.py
from dataclasses import dataclass

import pytest

from dazzle.render.ids import id_for


@dataclass(frozen=True)
class _FakeIRNode:
    kind: str
    name: str
    parent: "_FakeIRNode | None" = None


def test_id_for_surface() -> None:
    node = _FakeIRNode(kind="surface", name="task_list")
    assert id_for(node) == "surface-task_list"


def test_id_for_region() -> None:
    parent = _FakeIRNode(kind="surface", name="ops_dashboard")
    region = _FakeIRNode(kind="region", name="citation_graph", parent=parent)
    assert id_for(region) == "region-ops_dashboard-citation_graph"


def test_id_for_rejects_unknown_kind() -> None:
    node = _FakeIRNode(kind="moonbeam", name="foo")
    with pytest.raises(ValueError, match="unknown ir kind"):
        id_for(node)


def test_id_for_rejects_non_identifier_name() -> None:
    node = _FakeIRNode(kind="surface", name="task list with spaces")
    with pytest.raises(ValueError, match="invalid name"):
        id_for(node)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/test_ids.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.render.ids'`

- [ ] **Step 3: Implement the helper**

```python
# src/dazzle/render/ids.py
"""Single source of truth for element IDs.

Both renderers (Fragment, Jinja) call into here. Inline string literals for
ids in either renderer are forbidden by `tests/unit/test_no_inline_classes.py`
(added in Plan 3).
"""

import re
from typing import Protocol


_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KNOWN_KINDS = frozenset({
    "surface", "region", "fragment", "field", "action", "form", "row",
})


class IRNode(Protocol):
    kind: str
    name: str
    parent: "IRNode | None"


def id_for(node: IRNode) -> str:
    """Compute the DOM id for an IR node.

    Format: `<kind>-[<parent.name>-]<node.name>`. Walks the parent chain so a
    region's id includes its enclosing surface's name; this is what makes
    htmx targets stable across Fragment/Jinja boundary crossings.
    """
    if node.kind not in _KNOWN_KINDS:
        raise ValueError(f"unknown ir kind: {node.kind!r}")
    if not _VALID_NAME.match(node.name):
        raise ValueError(f"invalid name {node.name!r} for ir kind {node.kind!r}")

    parts = [node.kind]
    parent = node.parent
    while parent is not None:
        if not _VALID_NAME.match(parent.name):
            raise ValueError(f"invalid parent name {parent.name!r}")
        parts.append(parent.name)
        parent = parent.parent
    parts.append(node.name)

    # The list grew root-leaf because we walked parent-first; reverse the
    # parent chain segment so output reads outer→inner.
    head = parts[0]
    chain = list(reversed(parts[1:]))
    return "-".join([head, *chain])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/test_ids.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/ids.py tests/unit/render/test_ids.py
git commit -m "feat(render): id_for helper — single source of truth for element ids"
```

---

### Task 3: CSS class derivation helper

**Files:**
- Create: `src/dazzle/render/classes.py`
- Create: `tests/unit/render/test_classes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/test_classes.py
from dataclasses import dataclass

from dazzle.render.classes import classes_for


@dataclass(frozen=True)
class _Tokens:
    radius: str = "md"
    border: str = "subtle"


@dataclass(frozen=True)
class _CardLikeNode:
    kind: str = "card"


def test_classes_for_card_default_tokens() -> None:
    node = _CardLikeNode()
    tokens = _Tokens()
    classes = classes_for(node, tokens)
    assert "dz-card" in classes
    assert "dz-card--radius-md" in classes
    assert "dz-card--border-subtle" in classes


def test_classes_for_card_with_radius_override() -> None:
    node = _CardLikeNode()
    tokens = _Tokens(radius="lg")
    classes = classes_for(node, tokens)
    assert "dz-card--radius-lg" in classes
    assert "dz-card--radius-md" not in classes


def test_classes_for_returns_sorted_unique() -> None:
    node = _CardLikeNode()
    tokens = _Tokens()
    classes = classes_for(node, tokens)
    assert classes == sorted(set(classes))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/test_classes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.render.classes'`

- [ ] **Step 3: Implement the helper**

```python
# src/dazzle/render/classes.py
"""Single source of truth for CSS class names.

Both renderers (Fragment, Jinja) call into here. Inline class string literals
in either renderer are forbidden by `tests/unit/test_no_inline_classes.py`
(added in Plan 3).
"""

from typing import Protocol


class _ClassyNode(Protocol):
    kind: str


class _TokensProto(Protocol):
    pass  # accessed dynamically via getattr


def classes_for(node: _ClassyNode, tokens: object) -> list[str]:
    """Compute the CSS class list for an IR node, sorted and deduplicated.

    Format: `dz-<kind>` for the base class, `dz-<kind>--<token-name>-<value>`
    for each token-driven modifier. The `dz-` prefix namespaces all framework
    classes; app-local primitives may use their own prefix (e.g. `ak-` for
    Aegismark) but should not emit `dz-` classes.
    """
    base = f"dz-{node.kind}"
    out = {base}

    # Discover token modifiers via dataclass-style attribute introspection.
    # Specific kinds care about specific tokens; the mapping is enumerated here
    # rather than driven by reflection so the surface stays auditable.
    if node.kind == "card":
        for attr in ("radius", "border", "padding", "shadow"):
            value = getattr(tokens, attr, None)
            if value is not None:
                out.add(f"{base}--{attr}-{value}")
    elif node.kind == "button":
        for attr in ("variant", "size"):
            value = getattr(tokens, attr, None)
            if value is not None:
                out.add(f"{base}--{attr}-{value}")
    # Add new kinds here. Each must enumerate the token attrs that affect its
    # class output. Forgetting to add a kind means it gets only the base class
    # (safe default).

    return sorted(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/test_classes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/classes.py tests/unit/render/test_classes.py
git commit -m "feat(render): classes_for helper — single source of truth for css classes"
```

---

### Task 4: Token types

**Files:**
- Create: `src/dazzle/render/fragment/tokens.py`
- Create: `tests/unit/render/fragment/test_tokens.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_tokens.py
import pytest

from dazzle.render.fragment.tokens import (
    ButtonTokens,
    CardTokens,
    Palette,
    Spacing,
    TableTokens,
    Tokens,
)


def test_card_tokens_defaults() -> None:
    t = CardTokens()
    assert t.radius == "md"
    assert t.border == "subtle"
    assert t.padding == "normal"
    assert t.shadow == "none"


def test_card_tokens_invalid_radius() -> None:
    # Frozen dataclass with Literal types — mypy catches this at static time;
    # the runtime check in __post_init__ is the runtime safety net.
    with pytest.raises(ValueError, match="invalid radius"):
        CardTokens(radius="enormous")  # type: ignore[arg-type]


def test_button_tokens_defaults() -> None:
    t = ButtonTokens()
    assert t.variant == "secondary"
    assert t.size == "md"


def test_root_tokens_composes() -> None:
    t = Tokens()
    assert isinstance(t.card, CardTokens)
    assert isinstance(t.button, ButtonTokens)
    assert isinstance(t.table, TableTokens)
    assert isinstance(t.palette, Palette)
    assert isinstance(t.spacing, Spacing)


def test_tokens_is_frozen() -> None:
    t = Tokens()
    with pytest.raises(Exception):
        t.card = CardTokens(radius="lg")  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.render.fragment.tokens'`

- [ ] **Step 3: Implement the token types**

```python
# src/dazzle/render/fragment/tokens.py
"""Frozen-dataclass token types parameterising visual treatment.

Each token sub-type maps to a primitive that needs theming. The root `Tokens`
type composes them. Apps select a token sheet via the DSL `theme:` clause
(implemented in Plan 2) or override per-app in `app/ui/tokens.py`.
"""

from dataclasses import dataclass, field
from typing import Literal


_RADII = ("none", "sm", "md", "lg")
_BORDERS = ("none", "subtle", "emphatic")
_PADDINGS = ("compact", "normal", "comfortable")
_SHADOWS = ("none", "low", "elevated")
_BUTTON_VARIANTS = ("primary", "secondary", "danger", "ghost")
_SIZES = ("sm", "md", "lg")


@dataclass(frozen=True, slots=True)
class CardTokens:
    radius: Literal["none", "sm", "md", "lg"] = "md"
    border: Literal["none", "subtle", "emphatic"] = "subtle"
    padding: Literal["compact", "normal", "comfortable"] = "normal"
    shadow: Literal["none", "low", "elevated"] = "none"

    def __post_init__(self) -> None:
        if self.radius not in _RADII:
            raise ValueError(f"invalid radius {self.radius!r}")
        if self.border not in _BORDERS:
            raise ValueError(f"invalid border {self.border!r}")
        if self.padding not in _PADDINGS:
            raise ValueError(f"invalid padding {self.padding!r}")
        if self.shadow not in _SHADOWS:
            raise ValueError(f"invalid shadow {self.shadow!r}")


@dataclass(frozen=True, slots=True)
class ButtonTokens:
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"
    size: Literal["sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if self.variant not in _BUTTON_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")
        if self.size not in _SIZES:
            raise ValueError(f"invalid size {self.size!r}")


@dataclass(frozen=True, slots=True)
class TableTokens:
    density: Literal["compact", "normal", "comfortable"] = "normal"
    striped: bool = False

    def __post_init__(self) -> None:
        if self.density not in _PADDINGS:
            raise ValueError(f"invalid density {self.density!r}")


@dataclass(frozen=True, slots=True)
class Palette:
    """Semantic colour roles. Concrete hex values live in CSS custom properties;
    this type only names the role. Adding a colour here without a CSS custom
    property means undefined visual output."""

    accent: str = "default"
    surface: str = "default"
    danger: str = "default"


@dataclass(frozen=True, slots=True)
class Spacing:
    """Spacing scale. Values are token names mapped to rem in CSS custom props."""

    base: Literal["compact", "normal", "comfortable"] = "normal"

    def __post_init__(self) -> None:
        if self.base not in _PADDINGS:
            raise ValueError(f"invalid spacing base {self.base!r}")


@dataclass(frozen=True, slots=True)
class Tokens:
    card: CardTokens = field(default_factory=CardTokens)
    button: ButtonTokens = field(default_factory=ButtonTokens)
    table: TableTokens = field(default_factory=TableTokens)
    palette: Palette = field(default_factory=Palette)
    spacing: Spacing = field(default_factory=Spacing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_tokens.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/tokens.py tests/unit/render/fragment/test_tokens.py
git commit -m "feat(render): token types for fragment primitives"
```

---

### Task 5: Errors and RenderContext

**Files:**
- Create: `src/dazzle/render/fragment/errors.py`
- Create: `src/dazzle/render/fragment/context.py`
- Create: `tests/unit/render/fragment/test_context.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_context.py
from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import (
    CardSafetyError,
    FragmentError,
    HtmxBindingError,
)
from dazzle.render.fragment.tokens import Tokens, CardTokens


def test_render_context_default_tokens() -> None:
    ctx = RenderContext()
    assert isinstance(ctx.tokens, Tokens)


def test_render_context_explicit_tokens() -> None:
    custom = Tokens(card=CardTokens(radius="lg"))
    ctx = RenderContext(tokens=custom)
    assert ctx.tokens.card.radius == "lg"


def test_render_context_html_escape() -> None:
    ctx = RenderContext()
    assert ctx.escape("<script>") == "&lt;script&gt;"
    assert ctx.escape("safe text") == "safe text"


def test_card_safety_error_is_fragment_error() -> None:
    assert issubclass(CardSafetyError, FragmentError)
    assert issubclass(HtmxBindingError, FragmentError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement errors and context**

```python
# src/dazzle/render/fragment/errors.py
"""Exception hierarchy for the Fragment system.

All Fragment-construction or rendering errors derive from FragmentError so
callers can catch the family. Specific subclasses name the structural rule
that was violated, which becomes useful in test failure messages.
"""


class FragmentError(Exception):
    """Base class for all Fragment-system errors."""


class CardSafetyError(FragmentError):
    """Violation of card-safety invariants (no nested cards, no duplicate
    titles, etc). Replaces the runtime scanner at construction time."""


class HtmxBindingError(FragmentError):
    """An htmx attribute combination is incoherent (e.g. both hx_get and
    hx_post on the same primitive)."""


class PrimitiveRegistrationError(FragmentError):
    """A primitive was registered with a duplicate name or an unsupported
    shape."""
```

```python
# src/dazzle/render/fragment/context.py
"""RenderContext — carries tokens and helpers through the render pass.

Tokens flow via this context rather than as constructor args on every
primitive. Per-instance overrides remain possible (a primitive's own
`tokens` field, when present, takes precedence over the context's).
"""

import html
from dataclasses import dataclass, field

from dazzle.render.fragment.tokens import Tokens


@dataclass
class RenderContext:
    """Mutable context threaded through the renderer.

    Not frozen — the renderer may replace `tokens` when descending into a
    primitive that overrides them. Frozen-ness is a property of Fragments,
    not the rendering machinery.
    """

    tokens: Tokens = field(default_factory=Tokens)

    def escape(self, text: str) -> str:
        """HTML-escape user-facing text. Wraps stdlib `html.escape` so any
        future changes (e.g. additional attribute-context rules) live in
        one place."""
        return html.escape(text, quote=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_context.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/errors.py src/dazzle/render/fragment/context.py tests/unit/render/fragment/test_context.py
git commit -m "feat(render): RenderContext + error hierarchy"
```

---

### Task 6: htmx wrapper types

**Files:**
- Create: `src/dazzle/render/fragment/htmx.py`
- Create: `tests/unit/render/fragment/test_htmx_types.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_htmx_types.py
import pytest

from dazzle.render.fragment.htmx import HxTrigger, TargetSelector, URL


def test_url_accepts_relative_path() -> None:
    u = URL("/tasks/42")
    assert str(u) == "/tasks/42"


def test_url_rejects_javascript_scheme() -> None:
    with pytest.raises(ValueError, match="scheme"):
        URL("javascript:alert(1)")


def test_url_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="empty"):
        URL("")


def test_target_selector_id_form() -> None:
    t = TargetSelector("#region-task_list-main")
    assert str(t) == "#region-task_list-main"


def test_target_selector_keyword_form() -> None:
    assert str(TargetSelector("this")) == "this"
    assert str(TargetSelector("closest tr")) == "closest tr"


def test_target_selector_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid target selector"):
        TargetSelector("not a selector at all $$$")


def test_hx_trigger_simple_event() -> None:
    t = HxTrigger("click")
    assert str(t) == "click"


def test_hx_trigger_with_modifier() -> None:
    t = HxTrigger("keyup changed delay:500ms")
    assert str(t) == "keyup changed delay:500ms"


def test_hx_trigger_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        HxTrigger("")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_htmx_types.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement htmx wrapper types**

```python
# src/dazzle/render/fragment/htmx.py
"""Wrapper types for htmx attribute values.

These exist so that fields like `hx_target: TargetSelector | None` in primitives
carry validation at construction time, not at template-render time. A
TargetSelector that is constructed has been parsed and is structurally valid.
"""

import re
from dataclasses import dataclass


_DANGEROUS_SCHEMES = frozenset({"javascript", "data", "vbscript"})
_TARGET_KEYWORD = re.compile(r"^(this|closest [a-z][a-z0-9-]*|find [a-z][a-z0-9-]*|next|previous)$")
_TARGET_ID = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")
_TARGET_CLASS = re.compile(r"^\.[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class URL:
    """A validated URL for use in htmx attributes.

    Accepts relative paths (`/tasks/42`) and absolute http/https URLs. Rejects
    `javascript:`, `data:`, and `vbscript:` schemes which are XSS vectors.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("URL cannot be empty")
        if ":" in self.value:
            scheme = self.value.split(":", 1)[0].lower()
            if scheme in _DANGEROUS_SCHEMES:
                raise ValueError(f"disallowed scheme {scheme!r} in URL")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TargetSelector:
    """An htmx target selector. One of: `#id`, `.class`, or a keyword form
    (`this`, `closest <tag>`, `find <tag>`, `next`, `previous`).
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("TargetSelector cannot be empty")
        if not (
            _TARGET_KEYWORD.match(self.value)
            or _TARGET_ID.match(self.value)
            or _TARGET_CLASS.match(self.value)
        ):
            raise ValueError(f"invalid target selector {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HxTrigger:
    """An htmx trigger spec. Currently a thin wrapper around the trigger
    string (e.g. `click`, `keyup changed delay:500ms`). Validation here is
    light — only that the string is non-empty. Future versions may parse
    the trigger DSL more strictly."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("HxTrigger cannot be empty")

    def __str__(self) -> str:
        return self.value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_htmx_types.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/htmx.py tests/unit/render/fragment/test_htmx_types.py
git commit -m "feat(render): htmx wrapper types — URL, TargetSelector, HxTrigger"
```

---

### Task 7: Escape-hatch primitives (RawHTML, Slot)

**Files:**
- Create: `src/dazzle/render/fragment/escape.py`
- Create: `tests/unit/render/fragment/test_escape_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_escape_primitives.py
import pytest

from dazzle.render.fragment.escape import RawHTML, Slot


def test_raw_html_holds_string() -> None:
    r = RawHTML("<div>already rendered</div>")
    assert r.html == "<div>already rendered</div>"


def test_raw_html_rejects_none() -> None:
    with pytest.raises(TypeError):
        RawHTML(None)  # type: ignore[arg-type]


def test_slot_named() -> None:
    s = Slot(name="dynamic_region")
    assert s.name == "dynamic_region"


def test_slot_rejects_invalid_name() -> None:
    with pytest.raises(ValueError, match="invalid slot name"):
        Slot(name="dynamic region")


def test_raw_html_is_frozen() -> None:
    r = RawHTML("<p/>")
    with pytest.raises(Exception):
        r.html = "<div/>"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_escape_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement escape primitives**

```python
# src/dazzle/render/fragment/escape.py
"""Escape-hatch primitives — the explicit way out of the typed system.

`RawHTML` accepts an arbitrary HTML string and emits it verbatim. Used for
Jinja interop (Plan 3) and for the rare "this is too custom to model" case.
A lint count of `RawHTML(...)` occurrences per surface tracks migration
progress; downstream apps that have not migrated will have many, fully-
migrated example apps will have zero.

`Slot` names a hole in a Fragment tree that is filled later. Used by the
renderer for delayed/streamed content. Not a free-form escape — the slot
name must match the substitution map at render time.
"""

import re
from dataclasses import dataclass


_VALID_SLOT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class RawHTML:
    """Verbatim HTML emission. The audit-visible escape hatch."""

    html: str

    def __post_init__(self) -> None:
        if not isinstance(self.html, str):
            raise TypeError(f"RawHTML expects str, got {type(self.html).__name__}")


@dataclass(frozen=True, slots=True)
class Slot:
    """A named hole filled at render time."""

    name: str

    def __post_init__(self) -> None:
        if not _VALID_SLOT_NAME.match(self.name):
            raise ValueError(f"invalid slot name {self.name!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_escape_primitives.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/escape.py tests/unit/render/fragment/test_escape_primitives.py
git commit -m "feat(render): RawHTML and Slot escape-hatch primitives"
```

---

### Task 8: Primitive registry + @primitive decorator

**Files:**
- Create: `src/dazzle/render/fragment/registry.py`
- Create: `tests/unit/render/fragment/test_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_registry.py
from dataclasses import dataclass

import pytest

from dazzle.render.fragment.errors import PrimitiveRegistrationError
from dazzle.render.fragment.registry import PrimitiveRegistry, primitive


def test_register_and_resolve() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="test_widget", registry=registry)
    @dataclass(frozen=True, slots=True)
    class TestWidget:
        label: str

    assert registry.resolve("test_widget") is TestWidget


def test_duplicate_registration_rejected() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="dup", registry=registry)
    @dataclass(frozen=True, slots=True)
    class A:
        x: int = 0

    with pytest.raises(PrimitiveRegistrationError, match="already registered"):
        @primitive(name="dup", registry=registry)
        @dataclass(frozen=True, slots=True)
        class B:
            y: int = 0


def test_resolve_unknown_returns_none() -> None:
    registry = PrimitiveRegistry()
    assert registry.resolve("does_not_exist") is None


def test_registered_names_listing() -> None:
    registry = PrimitiveRegistry()

    @primitive(name="alpha", registry=registry)
    @dataclass(frozen=True, slots=True)
    class A:
        pass

    @primitive(name="beta", registry=registry)
    @dataclass(frozen=True, slots=True)
    class B:
        pass

    assert sorted(registry.registered_names()) == ["alpha", "beta"]


def test_registration_rejects_non_dataclass() -> None:
    registry = PrimitiveRegistry()
    with pytest.raises(PrimitiveRegistrationError, match="must be a dataclass"):
        @primitive(name="not_a_dataclass", registry=registry)
        class NotADataclass:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the registry**

```python
# src/dazzle/render/fragment/registry.py
"""Primitive registration — the extensibility seam.

Framework primitives are registered in `primitives/__init__.py` at module
load. App-local primitives use `@primitive(name="...")` in `app/ui/primitives/`,
registering against `RuntimeServices.primitive_registry` (Plan 2 wires this
up). The DSL `render: <name>` clause resolves through the registry.
"""

import dataclasses
from collections.abc import Callable
from typing import TypeVar

from dazzle.render.fragment.errors import PrimitiveRegistrationError


T = TypeVar("T", bound=type)


class PrimitiveRegistry:
    """Mutable registry mapping primitive names to dataclass types.

    Not thread-safe; registration happens at module import time before
    serving begins. Resolution is read-only at request time.
    """

    def __init__(self) -> None:
        self._types: dict[str, type] = {}

    def register(self, name: str, cls: type) -> None:
        if not dataclasses.is_dataclass(cls):
            raise PrimitiveRegistrationError(
                f"primitive {name!r} must be a dataclass; got {cls!r}"
            )
        if name in self._types:
            existing = self._types[name]
            raise PrimitiveRegistrationError(
                f"primitive {name!r} already registered to {existing!r}; "
                f"cannot re-register to {cls!r}"
            )
        self._types[name] = cls

    def resolve(self, name: str) -> type | None:
        return self._types.get(name)

    def registered_names(self) -> list[str]:
        return list(self._types.keys())


# Module-level default registry for framework primitives. App-local primitives
# pass their own registry via the decorator's `registry=` argument or wire up
# through RuntimeServices in Plan 2.
DEFAULT_REGISTRY = PrimitiveRegistry()


def primitive(
    *,
    name: str,
    registry: PrimitiveRegistry | None = None,
) -> Callable[[T], T]:
    """Decorator: register a dataclass as a Fragment primitive under `name`.

    Usage:

        @primitive(name="aegismark_kanban_board")
        @dataclass(frozen=True, slots=True)
        class AegismarkKanbanBoard:
            columns: tuple[KanbanColumn, ...]
    """
    target = registry if registry is not None else DEFAULT_REGISTRY

    def decorator(cls: T) -> T:
        target.register(name, cls)
        return cls

    return decorator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_registry.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/registry.py tests/unit/render/fragment/test_registry.py
git commit -m "feat(render): primitive registry + @primitive decorator"
```

---

## Phase 1 — Core primitives (leaf level)

### Task 9: Layout primitives (Stack, Row, Split, Grid)

**Files:**
- Create: `src/dazzle/render/fragment/primitives/layout.py`
- Create: `tests/unit/render/fragment/test_layout_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_layout_primitives.py
import pytest

from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack


def test_stack_holds_children() -> None:
    s = Stack(children=(_dummy("a"), _dummy("b")))
    assert len(s.children) == 2


def test_stack_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        Stack(children=())


def test_row_default_gap() -> None:
    r = Row(children=(_dummy("x"),))
    assert r.gap == "md"


def test_row_invalid_gap() -> None:
    with pytest.raises(ValueError, match="invalid gap"):
        Row(children=(_dummy("x"),), gap="ginormous")  # type: ignore[arg-type]


def test_split_two_panels() -> None:
    s = Split(start=_dummy("L"), end=_dummy("R"))
    assert s.start is not None
    assert s.end is not None


def test_grid_columns_clamp() -> None:
    with pytest.raises(ValueError, match="columns must be"):
        Grid(children=(_dummy("a"),), columns=0)
    with pytest.raises(ValueError, match="columns must be"):
        Grid(children=(_dummy("a"),), columns=13)


def _dummy(label: str):
    """Stand-in primitive for layout-children testing.

    Layout primitives accept any Fragment in their `children` field; until
    the Fragment union is declared in Task 16, we use a frozen dataclass
    placeholder that satisfies the structural type expected.
    """
    from dazzle.render.fragment.escape import RawHTML
    return RawHTML(html=f"<span>{label}</span>")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_layout_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement layout primitives**

```python
# src/dazzle/render/fragment/primitives/layout.py
"""Layout primitives — Stack (vertical), Row (horizontal), Split (two-panel),
Grid (n-column).

These are the structural building blocks that hold other primitives. They do
not have semantic meaning beyond layout — for semantic containers, see
`primitives/containers.py`.

NOTE: the `children` field type uses `tuple[object, ...]` for now; once Task 16
declares the `Fragment` union alias, this gets retyped to `tuple[Fragment, ...]`.
The type alias forward-reference would create a circular import, so we
intentionally use `object` as a structural placeholder until Task 16 wires it.
"""

from dataclasses import dataclass
from typing import Literal


_GAPS = ("none", "sm", "md", "lg")


@dataclass(frozen=True, slots=True)
class Stack:
    """Vertical stack of children."""

    children: tuple[object, ...]
    gap: Literal["none", "sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Stack requires at least one child")
        if self.gap not in _GAPS:
            raise ValueError(f"invalid gap {self.gap!r}")


@dataclass(frozen=True, slots=True)
class Row:
    """Horizontal row of children."""

    children: tuple[object, ...]
    gap: Literal["none", "sm", "md", "lg"] = "md"
    align: Literal["start", "center", "end", "stretch"] = "start"

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Row requires at least one child")
        if self.gap not in _GAPS:
            raise ValueError(f"invalid gap {self.gap!r}")
        if self.align not in ("start", "center", "end", "stretch"):
            raise ValueError(f"invalid align {self.align!r}")


@dataclass(frozen=True, slots=True)
class Split:
    """Two-panel split (typically inbox-like list/detail layouts)."""

    start: object
    end: object
    ratio: Literal["1:2", "1:1", "2:1", "1:3", "3:1"] = "1:2"

    def __post_init__(self) -> None:
        if self.ratio not in ("1:2", "1:1", "2:1", "1:3", "3:1"):
            raise ValueError(f"invalid ratio {self.ratio!r}")


@dataclass(frozen=True, slots=True)
class Grid:
    """N-column grid. Columns must be in [1, 12]."""

    children: tuple[object, ...]
    columns: int = 3

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Grid requires at least one child")
        if not (1 <= self.columns <= 12):
            raise ValueError(f"columns must be in [1, 12]; got {self.columns}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_layout_primitives.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/layout.py tests/unit/render/fragment/test_layout_primitives.py
git commit -m "feat(render): layout primitives — Stack, Row, Split, Grid"
```

---

### Task 10: Content primitives (Text, Heading, Icon, Badge, EmptyState, Skeleton)

**Files:**
- Create: `src/dazzle/render/fragment/primitives/content.py`
- Create: `tests/unit/render/fragment/test_content_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_content_primitives.py
import pytest

from dazzle.render.fragment.primitives.content import (
    Badge,
    EmptyState,
    Heading,
    Icon,
    Skeleton,
    Text,
)


def test_text_basic() -> None:
    t = Text("hello")
    assert t.body == "hello"
    assert t.tone == "default"


def test_text_invalid_tone() -> None:
    with pytest.raises(ValueError, match="invalid tone"):
        Text("hello", tone="rainbow")  # type: ignore[arg-type]


def test_heading_level_clamp() -> None:
    with pytest.raises(ValueError, match="level must be"):
        Heading("title", level=0)
    with pytest.raises(ValueError, match="level must be"):
        Heading("title", level=7)


def test_heading_default_level() -> None:
    h = Heading("title")
    assert h.level == 1


def test_icon_name() -> None:
    i = Icon(name="check")
    assert i.name == "check"
    assert i.size == "md"


def test_badge_variant() -> None:
    b = Badge(label="new", variant="success")
    assert b.variant == "success"


def test_empty_state_required_fields() -> None:
    e = EmptyState(title="Nothing here", description="Add an item to get started")
    assert e.title == "Nothing here"
    assert e.action is None


def test_skeleton_default_lines() -> None:
    s = Skeleton()
    assert s.lines == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_content_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement content primitives**

```python
# src/dazzle/render/fragment/primitives/content.py
"""Content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton.

These are the leaf-level visual primitives. They do not contain children
(except EmptyState, which contains an optional action). Most apps' visible
text routes through Text or Heading; status indicators route through Badge."""

from dataclasses import dataclass
from typing import Literal


_TONES = ("default", "muted", "danger", "success", "warning")
_BADGE_VARIANTS = ("default", "info", "success", "warning", "danger")
_ICON_SIZES = ("sm", "md", "lg")


@dataclass(frozen=True, slots=True)
class Text:
    body: str
    tone: Literal["default", "muted", "danger", "success", "warning"] = "default"

    def __post_init__(self) -> None:
        if self.tone not in _TONES:
            raise ValueError(f"invalid tone {self.tone!r}")


@dataclass(frozen=True, slots=True)
class Heading:
    body: str
    level: int = 1

    def __post_init__(self) -> None:
        if not (1 <= self.level <= 6):
            raise ValueError(f"level must be in [1, 6]; got {self.level}")


@dataclass(frozen=True, slots=True)
class Icon:
    name: str
    size: Literal["sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if self.size not in _ICON_SIZES:
            raise ValueError(f"invalid size {self.size!r}")


@dataclass(frozen=True, slots=True)
class Badge:
    label: str
    variant: Literal["default", "info", "success", "warning", "danger"] = "default"

    def __post_init__(self) -> None:
        if self.variant not in _BADGE_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")


@dataclass(frozen=True, slots=True)
class EmptyState:
    title: str
    description: str
    action: object | None = None  # Button | Link, retyped post-Task 16


@dataclass(frozen=True, slots=True)
class Skeleton:
    """Loading-state placeholder with N animated lines."""

    lines: int = 3

    def __post_init__(self) -> None:
        if self.lines < 1:
            raise ValueError(f"lines must be >= 1; got {self.lines}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_content_primitives.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/content.py tests/unit/render/fragment/test_content_primitives.py
git commit -m "feat(render): content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton"
```

---

### Task 11: Container primitives (Card, Region, Toolbar) — load-bearing invariants

This is the most important task in Phase 1. The `__post_init__` invariants here are what makes the scanner obsolete in Phase 9. Treat these tests as the structural contract for the design.

**Files:**
- Create: `src/dazzle/render/fragment/primitives/containers.py` (initial — Surface added in Task 13)
- Create: `tests/unit/render/fragment/test_container_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_container_primitives.py
"""Load-bearing tests: each scanner function in contract_checker.py maps to
one or more tests here that prove the violation is unrepresentable at the
type level. When Phase 9 deletes the scanner, these tests are what stays."""

import pytest

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.primitives.content import Heading, Text
from dazzle.render.fragment.primitives.containers import Card, Region, Toolbar


# === Card ===


def test_card_basic() -> None:
    c = Card(body=Text("contents"))
    assert c.body is not None
    assert c.header is None
    assert c.footer is None


def test_card_with_header_and_footer() -> None:
    c = Card(
        header=Text("title"),
        body=Text("body"),
        footer=Text("foot"),
    )
    assert c.header is not None


def test_card_cannot_directly_contain_card() -> None:
    """Replaces find_nested_chromes scanner."""
    inner = Card(body=Text("inner"))
    with pytest.raises(CardSafetyError, match="Card cannot directly contain another Card"):
        Card(body=inner)


def test_card_cannot_have_card_in_header() -> None:
    inner = Card(body=Text("inner"))
    with pytest.raises(CardSafetyError):
        Card(header=inner, body=Text("body"))


# === Region ===


def test_region_no_title_field() -> None:
    """Replaces find_duplicate_titles_in_cards scanner.

    Region structurally has no `title` field. The dashboard slot owns titles.
    """
    r = Region(kind="list", body=Text("rows"))
    assert not hasattr(r, "title")


def test_region_kind_required() -> None:
    """Region kind drives display behaviour; missing kind is a static error
    via the @dataclass decorator."""
    with pytest.raises(TypeError):
        Region(body=Text("rows"))  # type: ignore[call-arg]


def test_region_kind_validated() -> None:
    with pytest.raises(ValueError, match="invalid region kind"):
        Region(kind="moonbeam", body=Text("body"))  # type: ignore[arg-type]


# === Toolbar ===


def test_toolbar_with_actions() -> None:
    """Toolbar.actions: tuple of action-shaped objects. Type-level enforcement
    of "first action must not be hidden" lives in __post_init__ once Button
    is available (Task 12); for now we test the kind/order constraints."""
    t = Toolbar(label="Actions")
    assert t.actions == ()


def test_toolbar_label_required() -> None:
    with pytest.raises(TypeError):
        Toolbar()  # type: ignore[call-arg]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_container_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement container primitives (Card, Region, Toolbar)**

```python
# src/dazzle/render/fragment/primitives/containers.py
"""Container primitives — Card, Region, Toolbar.

The `__post_init__` invariants in this module are what makes the
contract_checker scanner obsolete. Each invariant here corresponds to a
named scanner function being retired in Phase 9.

Surface, Drawer, Modal, Tabs come later (Task 13) — they extend the
container vocabulary but do not introduce new card-safety invariants.
"""

from dataclasses import dataclass, field
from typing import Literal

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.tokens import CardTokens


_REGION_KINDS = ("list", "detail", "form", "dashboard", "kanban", "calendar", "report")


@dataclass(frozen=True, slots=True)
class Card:
    """Visual chrome — a bordered/padded surface wrapping content.

    Invariant: a Card cannot directly contain another Card (in body, header,
    or footer). Replaces the `find_nested_chromes` scanner.
    """

    body: object
    header: object | None = None
    footer: object | None = None
    tokens: CardTokens | None = None

    def __post_init__(self) -> None:
        for slot_name, slot_val in (("body", self.body), ("header", self.header), ("footer", self.footer)):
            if isinstance(slot_val, Card):
                raise CardSafetyError(
                    f"Card cannot directly contain another Card (in slot {slot_name!r}); "
                    f"if you need a nested card layout, compose via a layout primitive (Stack/Row) "
                    f"or unwrap the inner Card."
                )


@dataclass(frozen=True, slots=True)
class Region:
    """A semantic region inside a surface — list, detail, form, dashboard, etc.

    Region has NO `title` field by design. The dashboard slot (in Surface,
    Task 13) owns region titles. Replaces the `find_duplicate_titles_in_cards`
    scanner.
    """

    kind: Literal["list", "detail", "form", "dashboard", "kanban", "calendar", "report"]
    body: object

    def __post_init__(self) -> None:
        if self.kind not in _REGION_KINDS:
            raise ValueError(f"invalid region kind {self.kind!r}; must be one of {_REGION_KINDS}")


@dataclass(frozen=True, slots=True)
class Toolbar:
    """Action bar attached to a surface or region.

    `actions` carries the buttons in display order. Once Button is available
    (Task 12), the post-init enforces "first action cannot be visibility=hidden"
    — the type-level replacement for the find_hidden_primary_actions scanner.
    """

    label: str
    actions: tuple[object, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_container_primitives.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/containers.py tests/unit/render/fragment/test_container_primitives.py
git commit -m "feat(render): Card, Region, Toolbar — load-bearing card-safety invariants"
```

---

### Task 12: Interactive primitives (Button, Link, Interactive, InlineEdit)

**Files:**
- Create: `src/dazzle/render/fragment/primitives/interactive.py`
- Create: `tests/unit/render/fragment/test_interactive_primitives.py`
- Modify: `src/dazzle/render/fragment/primitives/containers.py` (add Toolbar primary-action invariant)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_interactive_primitives.py
import pytest

from dazzle.render.fragment.errors import CardSafetyError, HtmxBindingError
from dazzle.render.fragment.htmx import URL, TargetSelector
from dazzle.render.fragment.primitives.containers import Toolbar
from dazzle.render.fragment.primitives.content import Text
from dazzle.render.fragment.primitives.interactive import (
    Button,
    InlineEdit,
    Interactive,
    Link,
)


# === Button ===


def test_button_basic() -> None:
    b = Button(label="Save")
    assert b.label == "Save"
    assert b.variant == "secondary"


def test_button_htmx_get_requires_target() -> None:
    with pytest.raises(HtmxBindingError, match="needs hx_target"):
        Button(label="Refresh", hx_get=URL("/refresh"))


def test_button_htmx_get_with_target() -> None:
    b = Button(
        label="Refresh",
        hx_get=URL("/refresh"),
        hx_target=TargetSelector("#region-task_list-main"),
    )
    assert b.hx_get is not None


def test_button_rejects_both_get_and_post() -> None:
    with pytest.raises(HtmxBindingError, match="cannot have both"):
        Button(
            label="Confused",
            hx_get=URL("/g"),
            hx_post=URL("/p"),
            hx_target=TargetSelector("#x"),
        )


def test_button_visibility_default() -> None:
    b = Button(label="Save")
    assert b.visibility == "visible"


# === Toolbar primary-action invariant ===


def test_toolbar_first_action_cannot_be_hidden() -> None:
    """Replaces find_hidden_primary_actions scanner."""
    visible = Button(label="Save", variant="primary")
    hidden = Button(label="Save", variant="primary", visibility="hidden")

    Toolbar(label="ok", actions=(visible,))  # fine

    with pytest.raises(CardSafetyError, match="primary action cannot be hidden"):
        Toolbar(label="bad", actions=(hidden, visible))


# === Link ===


def test_link_basic() -> None:
    link = Link(label="Open", href=URL("/items/42"))
    assert link.label == "Open"
    assert str(link.href) == "/items/42"


# === Interactive wrapper ===


def test_interactive_wraps_child() -> None:
    inner = Text("clickable card")
    iw = Interactive(
        child=inner,
        hx_get=URL("/details/42"),
        hx_target=TargetSelector("#detail-pane"),
    )
    assert iw.child is inner


def test_interactive_requires_target() -> None:
    with pytest.raises(HtmxBindingError, match="needs hx_target"):
        Interactive(child=Text("x"), hx_get=URL("/x"))


# === InlineEdit ===


def test_inline_edit_field_required() -> None:
    ie = InlineEdit(field_name="title", value="Hello")
    assert ie.field_name == "title"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_interactive_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement interactive primitives**

```python
# src/dazzle/render/fragment/primitives/interactive.py
"""Interactive primitives — Button, Link, Interactive (wrapper), InlineEdit.

Buttons and Links carry typed htmx attributes. The Interactive wrapper
attaches htmx behaviour to any non-naturally-interactive child (clickable
card, hover-loaded row).

htmx invariants enforced at construction:
- A primitive cannot have both hx_get and hx_post.
- A primitive with any htmx-fetching attribute MUST have hx_target.

These replace the htmx-undefined-guards / preload-silence scanner tests.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.render.fragment.errors import HtmxBindingError
from dazzle.render.fragment.htmx import URL, HxTrigger, TargetSelector
from dazzle.render.fragment.tokens import ButtonTokens


_BUTTON_VARIANTS = ("primary", "secondary", "danger", "ghost")
_VISIBILITIES = ("visible", "hidden", "disabled")
_HX_SWAPS = ("innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none")


def _validate_htmx_pair(
    *,
    hx_get: URL | None,
    hx_post: URL | None,
    hx_target: TargetSelector | None,
    primitive_name: str,
) -> None:
    if hx_get is not None and hx_post is not None:
        raise HtmxBindingError(f"{primitive_name} cannot have both hx_get and hx_post")
    if (hx_get is not None or hx_post is not None) and hx_target is None:
        raise HtmxBindingError(
            f"{primitive_name} with hx_get/hx_post needs hx_target"
        )


@dataclass(frozen=True, slots=True)
class Button:
    label: str
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"
    visibility: Literal["visible", "hidden", "disabled"] = "visible"

    hx_get: URL | None = None
    hx_post: URL | None = None
    hx_target: TargetSelector | None = None
    hx_swap: Literal["innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none"] | None = None
    hx_trigger: HxTrigger | None = None
    hx_indicator: TargetSelector | None = None
    hx_confirm: str | None = None

    tokens: ButtonTokens | None = None

    def __post_init__(self) -> None:
        if self.variant not in _BUTTON_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")
        if self.visibility not in _VISIBILITIES:
            raise ValueError(f"invalid visibility {self.visibility!r}")
        if self.hx_swap is not None and self.hx_swap not in _HX_SWAPS:
            raise ValueError(f"invalid hx_swap {self.hx_swap!r}")
        _validate_htmx_pair(
            hx_get=self.hx_get,
            hx_post=self.hx_post,
            hx_target=self.hx_target,
            primitive_name="Button",
        )


@dataclass(frozen=True, slots=True)
class Link:
    label: str
    href: URL


@dataclass(frozen=True, slots=True)
class Interactive:
    """Wraps any Fragment with htmx behaviour. Used sparingly — naturally-
    interactive primitives (Button, Link, InlineEdit) carry their own htmx
    fields. Interactive exists for clickable cards, hover-loaded rows, etc."""

    child: object
    hx_get: URL | None = None
    hx_post: URL | None = None
    hx_target: TargetSelector | None = None
    hx_swap: Literal["innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none"] | None = None
    hx_trigger: HxTrigger | None = None

    def __post_init__(self) -> None:
        _validate_htmx_pair(
            hx_get=self.hx_get,
            hx_post=self.hx_post,
            hx_target=self.hx_target,
            primitive_name="Interactive",
        )


@dataclass(frozen=True, slots=True)
class InlineEdit:
    """Click-to-edit field. Compiles to an htmx-driven swap.

    The `field_name` references an entity field in the surrounding IR; the
    renderer wires up hx_post to the field-update endpoint.
    """

    field_name: str
    value: str
    placeholder: str = ""
```

- [ ] **Step 4: Update Toolbar with primary-action invariant**

Edit `src/dazzle/render/fragment/primitives/containers.py` — replace the existing `Toolbar` definition with one that enforces the primary-action visibility invariant:

```python
# Add at top of containers.py (in the existing import block):
from dazzle.render.fragment.errors import CardSafetyError


# Replace the existing Toolbar class definition:
@dataclass(frozen=True, slots=True)
class Toolbar:
    """Action bar attached to a surface or region.

    Invariant: the FIRST action cannot have visibility="hidden". Replaces the
    find_hidden_primary_actions scanner. The first action is the primary
    action of the toolbar; hiding it makes the toolbar unfindable.
    """

    label: str
    actions: tuple[object, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.actions:
            first = self.actions[0]
            visibility = getattr(first, "visibility", "visible")
            if visibility == "hidden":
                raise CardSafetyError(
                    "Toolbar primary action cannot be hidden; first action determines "
                    "toolbar discoverability. If the action is conditionally available, "
                    "use visibility='disabled' instead."
                )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_interactive_primitives.py tests/unit/render/fragment/test_container_primitives.py -v`
Expected: PASS (16 tests across both files)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/render/fragment/primitives/interactive.py src/dazzle/render/fragment/primitives/containers.py tests/unit/render/fragment/test_interactive_primitives.py
git commit -m "feat(render): interactive primitives + Toolbar primary-action invariant"
```

---

## Phase 2 — Structural primitives

### Task 13: Surface, Tabs, Drawer, Modal

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/containers.py` (add Surface, Tabs, Drawer, Modal)
- Modify: `tests/unit/render/fragment/test_container_primitives.py` (add Surface tests)

- [ ] **Step 1: Add the failing tests to the existing test file**

Append to `tests/unit/render/fragment/test_container_primitives.py`:

```python
from dazzle.render.fragment.primitives.containers import Drawer, Modal, Surface, Tabs


# === Surface ===


def test_surface_required_body() -> None:
    s = Surface(body=Text("contents"))
    assert s.body is not None
    assert s.header is None
    assert s.footer is None


def test_surface_has_no_title_field() -> None:
    """Surface has fixed slots (header, body, footer); a title slot would
    re-introduce the duplicate-titles violation. The header IS the title slot."""
    s = Surface(body=Text("body"))
    assert not hasattr(s, "title")


def test_surface_does_not_admit_card_as_header() -> None:
    """A header is text-shaped; a Card-as-header re-introduces nested-chrome."""
    inner_card = Card(body=Text("nested"))
    with pytest.raises(CardSafetyError, match="header cannot be a Card"):
        Surface(header=inner_card, body=Text("body"))


# === Tabs ===


def test_tabs_requires_panels() -> None:
    with pytest.raises(ValueError, match="at least one tab"):
        Tabs(tabs=())


def test_tabs_panel_construction() -> None:
    t = Tabs(
        tabs=(
            ("overview", Text("o")),
            ("details", Text("d")),
        )
    )
    assert len(t.tabs) == 2


def test_tabs_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate tab key"):
        Tabs(
            tabs=(
                ("a", Text("1")),
                ("a", Text("2")),
            )
        )


# === Drawer + Modal ===


def test_drawer_side_default() -> None:
    d = Drawer(body=Text("contents"))
    assert d.side == "right"


def test_drawer_invalid_side() -> None:
    with pytest.raises(ValueError, match="invalid side"):
        Drawer(body=Text("body"), side="up")  # type: ignore[arg-type]


def test_modal_size_default() -> None:
    m = Modal(body=Text("contents"))
    assert m.size == "md"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/unit/render/fragment/test_container_primitives.py -v`
Expected: PASS for original 9 tests, FAIL for 9 new tests with `ImportError: cannot import name 'Surface'`.

- [ ] **Step 3: Add structural containers to containers.py**

Append to `src/dazzle/render/fragment/primitives/containers.py`:

```python
@dataclass(frozen=True, slots=True)
class Surface:
    """Top-level rendered surface — list, detail, form, dashboard, etc.

    Surface has THREE slots and only three: header, body, footer. There is
    intentionally no `title` slot; the header carries titling. This is the
    structural invariant that prevents duplicate-title violations at the
    surface level (regions are constrained the same way in `Region`).

    A Card cannot occupy the header slot — that would re-introduce nested
    chrome. Body and footer are unconstrained for chrome since their content
    is typically the "inside" of the surface where Cards are appropriate.
    """

    body: object
    header: object | None = None
    footer: object | None = None

    def __post_init__(self) -> None:
        if isinstance(self.header, Card):
            raise CardSafetyError(
                "Surface header cannot be a Card; the surface IS the chrome. "
                "Use plain Text/Heading/Toolbar in the header slot."
            )


@dataclass(frozen=True, slots=True)
class Tabs:
    """Tabbed container. Each tab is `(key, Fragment)` — keys must be unique."""

    tabs: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not self.tabs:
            raise ValueError("Tabs requires at least one tab")
        seen: set[str] = set()
        for key, _panel in self.tabs:
            if key in seen:
                raise ValueError(f"duplicate tab key {key!r}")
            seen.add(key)


@dataclass(frozen=True, slots=True)
class Drawer:
    """Slide-over panel. Anchored to a screen edge."""

    body: object
    side: Literal["left", "right", "top", "bottom"] = "right"

    def __post_init__(self) -> None:
        if self.side not in ("left", "right", "top", "bottom"):
            raise ValueError(f"invalid side {self.side!r}")


@dataclass(frozen=True, slots=True)
class Modal:
    """Centered overlay dialog."""

    body: object
    size: Literal["sm", "md", "lg", "xl"] = "md"

    def __post_init__(self) -> None:
        if self.size not in ("sm", "md", "lg", "xl"):
            raise ValueError(f"invalid size {self.size!r}")
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/unit/render/fragment/test_container_primitives.py -v`
Expected: PASS (18 tests total: 9 original + 9 new)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/containers.py tests/unit/render/fragment/test_container_primitives.py
git commit -m "feat(render): structural containers — Surface, Tabs, Drawer, Modal"
```

---

### Task 14: Form primitives (FormStack, Field, Combobox, Submit)

**Files:**
- Create: `src/dazzle/render/fragment/primitives/forms.py`
- Create: `tests/unit/render/fragment/test_form_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_form_primitives.py
import pytest

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, Submit


def test_form_stack_requires_action() -> None:
    fs = FormStack(action=URL("/tasks/create"), fields=(Field(name="title", label="Title"),))
    assert fs.action is not None
    assert fs.method == "POST"


def test_form_stack_rejects_no_fields() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        FormStack(action=URL("/x"), fields=())


def test_field_required() -> None:
    f = Field(name="title", label="Title")
    assert f.required is False
    assert f.kind == "text"


def test_field_invalid_kind() -> None:
    with pytest.raises(ValueError, match="invalid field kind"):
        Field(name="title", label="Title", kind="moonbeam")  # type: ignore[arg-type]


def test_combobox_options_required() -> None:
    with pytest.raises(ValueError, match="at least one option"):
        Combobox(name="status", label="Status", options=())


def test_combobox_option_pairs() -> None:
    c = Combobox(
        name="status",
        label="Status",
        options=(("open", "Open"), ("closed", "Closed")),
    )
    assert len(c.options) == 2


def test_submit_label_required() -> None:
    s = Submit(label="Save changes")
    assert s.label == "Save changes"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_form_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement form primitives**

```python
# src/dazzle/render/fragment/primitives/forms.py
"""Form primitives — FormStack (the form container), Field (single input),
Combobox (typeahead select), Submit (form action button).

InlineEdit lives in `interactive.py` because it's not part of a form-wide
submit cycle — it's a one-field htmx-swap.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.render.fragment.htmx import URL


_FIELD_KINDS = (
    "text", "email", "password", "number", "date", "datetime", "time",
    "textarea", "checkbox", "radio", "url", "tel",
)
_METHODS = ("GET", "POST")


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    label: str
    kind: Literal[
        "text", "email", "password", "number", "date", "datetime", "time",
        "textarea", "checkbox", "radio", "url", "tel",
    ] = "text"
    required: bool = False
    placeholder: str = ""
    initial_value: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _FIELD_KINDS:
            raise ValueError(f"invalid field kind {self.kind!r}")


@dataclass(frozen=True, slots=True)
class Combobox:
    name: str
    label: str
    options: tuple[tuple[str, str], ...]
    required: bool = False
    initial_value: str = ""

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("Combobox requires at least one option")


@dataclass(frozen=True, slots=True)
class Submit:
    label: str
    variant: Literal["primary", "secondary", "danger"] = "primary"


@dataclass(frozen=True, slots=True)
class FormStack:
    action: URL
    fields: tuple[object, ...]  # Field | Combobox
    method: Literal["GET", "POST"] = "POST"
    submit: Submit | None = None

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FormStack requires at least one field")
        if self.method not in _METHODS:
            raise ValueError(f"invalid method {self.method!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_form_primitives.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/forms.py tests/unit/render/fragment/test_form_primitives.py
git commit -m "feat(render): form primitives — FormStack, Field, Combobox, Submit"
```

---

### Task 15: Data primitives (Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard, CalendarGrid)

**Files:**
- Create: `src/dazzle/render/fragment/primitives/data.py`
- Create: `tests/unit/render/fragment/test_data_primitives.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_data_primitives.py
import pytest

from dazzle.render.fragment.primitives.data import (
    BarChart,
    CalendarGrid,
    KanbanBoard,
    KPI,
    PivotTable,
    Table,
    Timeline,
)


# === Table ===


def test_table_columns_and_rows() -> None:
    t = Table(
        columns=("title", "status"),
        rows=(("Buy milk", "open"), ("Walk dog", "done")),
    )
    assert len(t.rows) == 2


def test_table_rejects_no_columns() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        Table(columns=(), rows=(("x",),))


def test_table_row_arity_must_match_columns() -> None:
    with pytest.raises(ValueError, match="row arity"):
        Table(columns=("a", "b"), rows=(("only_one",),))


# === KPI ===


def test_kpi_basic() -> None:
    k = KPI(label="Revenue", value="$42k", trend="up")
    assert k.trend == "up"


def test_kpi_invalid_trend() -> None:
    with pytest.raises(ValueError, match="invalid trend"):
        KPI(label="x", value="0", trend="sideways")  # type: ignore[arg-type]


# === BarChart / PivotTable ===


def test_bar_chart_buckets() -> None:
    b = BarChart(label="Tasks by status", buckets=(("open", 3), ("done", 7)))
    assert len(b.buckets) == 2


def test_bar_chart_rejects_no_buckets() -> None:
    with pytest.raises(ValueError, match="at least one bucket"):
        BarChart(label="x", buckets=())


def test_pivot_table_dimensions() -> None:
    p = PivotTable(
        label="System x severity",
        rows=("auth", "billing"),
        columns=("low", "high"),
        cells={
            ("auth", "low"): 1,
            ("auth", "high"): 2,
            ("billing", "low"): 0,
            ("billing", "high"): 5,
        },
    )
    assert p.cells[("auth", "high")] == 2


# === Timeline / Kanban / Calendar ===


def test_timeline_events() -> None:
    t = Timeline(events=(("created", "2026-05-05"),))
    assert len(t.events) == 1


def test_kanban_columns() -> None:
    k = KanbanBoard(columns=(("open", ()), ("done", ())))
    assert len(k.columns) == 2


def test_calendar_view_default() -> None:
    c = CalendarGrid()
    assert c.view == "month"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_data_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement data primitives**

```python
# src/dazzle/render/fragment/primitives/data.py
"""Data primitives — Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard,
CalendarGrid.

These are display-only primitives that render structured data. They do not
construct queries themselves — they accept already-aggregated data shaped
to match the IR's aggregate result. The IR-to-Fragment binding lives in the
renderer's surface-mode adapters (added in Plan 2).

Most invariants here concentrate around shape mismatches: a Table's row
arity must match its column count; a PivotTable's cells must reference
declared rows and columns; etc.
"""

from dataclasses import dataclass, field
from typing import Literal


_TRENDS = ("up", "down", "flat")
_CALENDAR_VIEWS = ("day", "week", "month")


@dataclass(frozen=True, slots=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("Table requires at least one column")
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row arity mismatch at index {i}: row has {len(row)} cells, "
                    f"columns has {len(self.columns)}"
                )


@dataclass(frozen=True, slots=True)
class KPI:
    label: str
    value: str
    trend: Literal["up", "down", "flat"] = "flat"
    delta: str = ""

    def __post_init__(self) -> None:
        if self.trend not in _TRENDS:
            raise ValueError(f"invalid trend {self.trend!r}")


@dataclass(frozen=True, slots=True)
class BarChart:
    label: str
    buckets: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.buckets:
            raise ValueError("BarChart requires at least one bucket")


@dataclass(frozen=True, slots=True)
class PivotTable:
    label: str
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: dict[tuple[str, str], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("PivotTable requires at least one row dimension")
        if not self.columns:
            raise ValueError("PivotTable requires at least one column dimension")
        for (r, c), _val in self.cells.items():
            if r not in self.rows:
                raise ValueError(f"cell row {r!r} not in declared rows {self.rows}")
            if c not in self.columns:
                raise ValueError(f"cell column {c!r} not in declared columns {self.columns}")


@dataclass(frozen=True, slots=True)
class Timeline:
    events: tuple[tuple[str, str], ...]  # (label, iso-date)


@dataclass(frozen=True, slots=True)
class KanbanBoard:
    columns: tuple[tuple[str, tuple[object, ...]], ...]  # (column_key, items)

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("KanbanBoard requires at least one column")


@dataclass(frozen=True, slots=True)
class CalendarGrid:
    view: Literal["day", "week", "month"] = "month"
    events: tuple[tuple[str, str], ...] = ()  # (label, iso-date)

    def __post_init__(self) -> None:
        if self.view not in _CALENDAR_VIEWS:
            raise ValueError(f"invalid view {self.view!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_data_primitives.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/data.py tests/unit/render/fragment/test_data_primitives.py
git commit -m "feat(render): data primitives — Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard, CalendarGrid"
```

---

### Task 16: Fragment type alias and primitives package exports

**Files:**
- Create: `src/dazzle/render/fragment/primitives/_base.py`
- Modify: `src/dazzle/render/fragment/primitives/__init__.py`
- Modify: `src/dazzle/render/fragment/__init__.py`
- Create: `tests/unit/render/fragment/test_fragment_alias.py`

This task wires up the type alias. After this, every primitive's `object`-typed children/body fields can be re-typed to `Fragment` if desired, but mypy will accept the structural compatibility either way; we leave the existing fields as `object` to avoid the circular-import dance and rely on the renderer's match-dispatch for runtime exhaustiveness.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/render/fragment/test_fragment_alias.py
"""Verify the Fragment alias names every primitive type. Adding a new
primitive without adding it here is what we want this test to catch."""

import typing

from dazzle.render.fragment import Fragment


def test_fragment_alias_includes_all_primitives() -> None:
    args = typing.get_args(Fragment)
    names = {t.__name__ for t in args}
    expected = {
        # layout
        "Stack", "Row", "Split", "Grid",
        # containers
        "Surface", "Card", "Region", "Toolbar", "Drawer", "Modal", "Tabs",
        # content
        "Text", "Heading", "Icon", "Badge", "EmptyState", "Skeleton",
        # interactive
        "Button", "Link", "InlineEdit", "Interactive",
        # data
        "Table", "KanbanBoard", "CalendarGrid", "Timeline",
        "KPI", "BarChart", "PivotTable",
        # forms
        "FormStack", "Field", "Combobox", "Submit",
        # escape
        "RawHTML", "Slot",
    }
    assert names == expected, f"missing: {expected - names}; extra: {names - expected}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/render/fragment/test_fragment_alias.py -v`
Expected: FAIL with `ImportError: cannot import name 'Fragment'`

- [ ] **Step 3: Declare the Fragment alias**

```python
# src/dazzle/render/fragment/primitives/_base.py
"""The Fragment type alias — discriminated union of every framework primitive.

Importers should prefer `from dazzle.render.fragment import Fragment` over
reaching into this module directly.
"""

from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives.containers import (
    Card, Drawer, Modal, Region, Surface, Tabs, Toolbar,
)
from dazzle.render.fragment.primitives.content import (
    Badge, EmptyState, Heading, Icon, Skeleton, Text,
)
from dazzle.render.fragment.primitives.data import (
    BarChart, CalendarGrid, KanbanBoard, KPI, PivotTable, Table, Timeline,
)
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, Submit
from dazzle.render.fragment.primitives.interactive import (
    Button, InlineEdit, Interactive, Link,
)
from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack


Fragment = (
    # Layout
    Stack | Row | Split | Grid
    # Containers
    | Surface | Card | Region | Toolbar | Drawer | Modal | Tabs
    # Content
    | Text | Heading | Icon | Badge | EmptyState | Skeleton
    # Interactive
    | Button | Link | InlineEdit | Interactive
    # Data
    | Table | KanbanBoard | CalendarGrid | Timeline | KPI | BarChart | PivotTable
    # Forms
    | FormStack | Field | Combobox | Submit
    # Escape hatches
    | RawHTML | Slot
)
```

```python
# src/dazzle/render/fragment/primitives/__init__.py
"""Framework primitive types."""

from dazzle.render.fragment.primitives._base import Fragment
from dazzle.render.fragment.primitives.containers import (
    Card, Drawer, Modal, Region, Surface, Tabs, Toolbar,
)
from dazzle.render.fragment.primitives.content import (
    Badge, EmptyState, Heading, Icon, Skeleton, Text,
)
from dazzle.render.fragment.primitives.data import (
    BarChart, CalendarGrid, KanbanBoard, KPI, PivotTable, Table, Timeline,
)
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, Submit
from dazzle.render.fragment.primitives.interactive import (
    Button, InlineEdit, Interactive, Link,
)
from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack


__all__ = [
    "Fragment",
    # layout
    "Stack", "Row", "Split", "Grid",
    # containers
    "Surface", "Card", "Region", "Toolbar", "Drawer", "Modal", "Tabs",
    # content
    "Text", "Heading", "Icon", "Badge", "EmptyState", "Skeleton",
    # interactive
    "Button", "Link", "InlineEdit", "Interactive",
    # data
    "Table", "KanbanBoard", "CalendarGrid", "Timeline",
    "KPI", "BarChart", "PivotTable",
    # forms
    "FormStack", "Field", "Combobox", "Submit",
]
```

```python
# src/dazzle/render/fragment/__init__.py
"""Typed Fragment system — frozen-dataclass primitives + HTML renderer."""

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import (
    CardSafetyError,
    FragmentError,
    HtmxBindingError,
    PrimitiveRegistrationError,
)
from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.htmx import URL, HxTrigger, TargetSelector
from dazzle.render.fragment.primitives import (
    Badge, BarChart, Button, CalendarGrid, Card, Combobox, Drawer, EmptyState,
    Field, FormStack, Fragment, Grid, Heading, Icon, InlineEdit, Interactive,
    KanbanBoard, KPI, Link, Modal, PivotTable, Region, Row, Skeleton, Split,
    Stack, Submit, Surface, Table, Tabs, Text, Timeline, Toolbar,
)
from dazzle.render.fragment.registry import DEFAULT_REGISTRY, PrimitiveRegistry, primitive
from dazzle.render.fragment.tokens import (
    ButtonTokens,
    CardTokens,
    Palette,
    Spacing,
    TableTokens,
    Tokens,
)


__all__ = [
    # core
    "Fragment",
    "RenderContext",
    # errors
    "FragmentError", "CardSafetyError", "HtmxBindingError", "PrimitiveRegistrationError",
    # escape hatches
    "RawHTML", "Slot",
    # htmx wrappers
    "URL", "TargetSelector", "HxTrigger",
    # registry
    "primitive", "PrimitiveRegistry", "DEFAULT_REGISTRY",
    # tokens
    "Tokens", "CardTokens", "ButtonTokens", "TableTokens", "Palette", "Spacing",
    # primitives — layout
    "Stack", "Row", "Split", "Grid",
    # primitives — containers
    "Surface", "Card", "Region", "Toolbar", "Drawer", "Modal", "Tabs",
    # primitives — content
    "Text", "Heading", "Icon", "Badge", "EmptyState", "Skeleton",
    # primitives — interactive
    "Button", "Link", "InlineEdit", "Interactive",
    # primitives — data
    "Table", "KanbanBoard", "CalendarGrid", "Timeline", "KPI", "BarChart", "PivotTable",
    # primitives — forms
    "FormStack", "Field", "Combobox", "Submit",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_fragment_alias.py -v`
Expected: PASS (1 test)

Then run the entire render test suite:

Run: `pytest tests/unit/render/ -v`
Expected: PASS for all tests across all test files (cumulative ~80 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/primitives/_base.py src/dazzle/render/fragment/primitives/__init__.py src/dazzle/render/fragment/__init__.py tests/unit/render/fragment/test_fragment_alias.py
git commit -m "feat(render): Fragment type alias + public package exports"
```

---

## Phase 3 — First renderer

### Task 17: FragmentRenderer skeleton + match-dispatch

**Files:**
- Create: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_skeleton.py`

The renderer is a single class with a `render(fragment) -> str` method that match-dispatches on the Fragment union and delegates to a per-primitive emit method. We start with a skeleton that handles `RawHTML`, `Slot`, `Text`, and `Heading`, then fill in additional primitives in subsequent tasks.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_skeleton.py
import pytest

from dazzle.render.fragment import (
    FragmentError,
    Heading,
    RawHTML,
    RenderContext,
    Slot,
    Text,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_raw_html_passthrough() -> None:
    r = FragmentRenderer()
    out = r.render(RawHTML("<p>hi</p>"))
    assert out == "<p>hi</p>"


def test_render_text_escapes() -> None:
    r = FragmentRenderer()
    out = r.render(Text("<script>"))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_text_default_tone() -> None:
    r = FragmentRenderer()
    out = r.render(Text("hello"))
    assert "hello" in out
    assert "dz-text" in out


def test_render_heading_level() -> None:
    r = FragmentRenderer()
    out = r.render(Heading("Title", level=2))
    assert out.startswith("<h2")
    assert "Title" in out


def test_render_unfilled_slot_raises() -> None:
    """A Slot that reaches the renderer without a substitution map is a
    programmer error, not user data — fail loudly."""
    r = FragmentRenderer()
    with pytest.raises(FragmentError, match="unfilled slot"):
        r.render(Slot(name="dynamic"))


def test_render_with_explicit_context() -> None:
    r = FragmentRenderer()
    ctx = RenderContext()
    out = r.render(Text("hello"), ctx=ctx)
    assert "hello" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_skeleton.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the renderer skeleton**

```python
# src/dazzle/render/fragment/renderer.py
"""FragmentRenderer — emits HTML from Fragment trees.

Single-class renderer. The `render` method match-dispatches on the Fragment
union; per-primitive emit methods produce HTML strings. The match block is
the runtime exhaustiveness check — adding a new primitive without adding a
match arm causes mypy to flag the unreachable case (with `--strict`) and
the test_fragment_exhaustiveness test (Task 24) to fail.
"""

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives import (
    Badge, BarChart, Button, CalendarGrid, Card, Combobox, Drawer, EmptyState,
    Field, FormStack, Fragment, Grid, Heading, Icon, InlineEdit, Interactive,
    KanbanBoard, KPI, Link, Modal, PivotTable, Region, Row, Skeleton, Split,
    Stack, Submit, Surface, Table, Tabs, Text, Timeline, Toolbar,
)


class FragmentRenderer:
    """Emit HTML from a Fragment tree.

    Stateless — a single instance can be reused across requests. The
    RenderContext is per-render-call and threads tokens through descent.
    """

    def render(self, fragment: Fragment, ctx: RenderContext | None = None) -> str:
        ctx = ctx if ctx is not None else RenderContext()
        return self._emit(fragment, ctx)

    def _emit(self, fragment: Fragment, ctx: RenderContext) -> str:
        match fragment:
            # Escape hatches first — most likely path is RawHTML interop
            case RawHTML(html=html):
                return html
            case Slot(name=name):
                raise FragmentError(
                    f"unfilled slot {name!r} reached the renderer; "
                    f"slots must be substituted before render() is called"
                )
            # Content
            case Text():
                return self._emit_text(fragment, ctx)
            case Heading():
                return self._emit_heading(fragment, ctx)
            # Subsequent tasks (18-23) extend the match block.
            case _:
                raise FragmentError(
                    f"renderer has no emit for {type(fragment).__name__!r} yet — "
                    f"add a match arm in FragmentRenderer._emit"
                )

    # --- per-primitive emitters ---

    def _emit_text(self, t: Text, ctx: RenderContext) -> str:
        body = ctx.escape(t.body)
        cls = f"dz-text dz-text--tone-{t.tone}"
        return f'<span class="{cls}">{body}</span>'

    def _emit_heading(self, h: Heading, ctx: RenderContext) -> str:
        body = ctx.escape(h.body)
        cls = f"dz-heading dz-heading--level-{h.level}"
        return f'<h{h.level} class="{cls}">{body}</h{h.level}>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_skeleton.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_skeleton.py
git commit -m "feat(render): FragmentRenderer skeleton — Text, Heading, RawHTML, Slot"
```

---

### Task 18: Render layout primitives (Stack, Row, Split, Grid)

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_layout.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_layout.py
from dazzle.render.fragment import Grid, Row, Split, Stack, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_stack_with_two_children() -> None:
    r = FragmentRenderer()
    out = r.render(Stack(children=(Text("a"), Text("b"))))
    assert out.count("dz-text") == 2
    assert "dz-stack" in out
    assert "dz-stack--gap-md" in out


def test_render_row_alignment() -> None:
    r = FragmentRenderer()
    out = r.render(Row(children=(Text("x"),), align="center"))
    assert "dz-row--align-center" in out


def test_render_split() -> None:
    r = FragmentRenderer()
    out = r.render(Split(start=Text("L"), end=Text("R"), ratio="1:2"))
    assert "dz-split--ratio-1_2" in out
    assert out.count("dz-text") == 2


def test_render_grid_columns_class() -> None:
    r = FragmentRenderer()
    out = r.render(Grid(children=(Text("x"),), columns=4))
    assert "dz-grid--columns-4" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_layout.py -v`
Expected: FAIL — the renderer raises `FragmentError: renderer has no emit for 'Stack' yet`

- [ ] **Step 3: Add layout emitters to the renderer**

In `src/dazzle/render/fragment/renderer.py`, extend the match block in `_emit` (insert before the `case _:` default arm):

```python
            # Layout
            case Stack():
                return self._emit_stack(fragment, ctx)
            case Row():
                return self._emit_row(fragment, ctx)
            case Split():
                return self._emit_split(fragment, ctx)
            case Grid():
                return self._emit_grid(fragment, ctx)
```

And add the emit methods to the `FragmentRenderer` class:

```python
    def _emit_stack(self, s: Stack, ctx: RenderContext) -> str:
        cls = f"dz-stack dz-stack--gap-{s.gap}"
        body = "".join(self._emit(c, ctx) for c in s.children)
        return f'<div class="{cls}">{body}</div>'

    def _emit_row(self, r: Row, ctx: RenderContext) -> str:
        cls = f"dz-row dz-row--gap-{r.gap} dz-row--align-{r.align}"
        body = "".join(self._emit(c, ctx) for c in r.children)
        return f'<div class="{cls}">{body}</div>'

    def _emit_split(self, s: Split, ctx: RenderContext) -> str:
        # The colon in ratio strings is invalid in CSS class names; replace
        # with underscore. Both renderers (here and Jinja) must use the same
        # convention — see classes.py for the shared rule once we move it.
        ratio_class = s.ratio.replace(":", "_")
        cls = f"dz-split dz-split--ratio-{ratio_class}"
        start_html = self._emit(s.start, ctx)
        end_html = self._emit(s.end, ctx)
        return (
            f'<div class="{cls}">'
            f'<div class="dz-split__start">{start_html}</div>'
            f'<div class="dz-split__end">{end_html}</div>'
            f'</div>'
        )

    def _emit_grid(self, g: Grid, ctx: RenderContext) -> str:
        cls = f"dz-grid dz-grid--columns-{g.columns}"
        body = "".join(self._emit(c, ctx) for c in g.children)
        return f'<div class="{cls}">{body}</div>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_layout.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_layout.py
git commit -m "feat(render): renderer support for Stack, Row, Split, Grid"
```

---

### Task 19: Render container primitives (Surface, Card, Region, Toolbar, Drawer, Modal, Tabs)

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_containers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_containers.py
from dazzle.render.fragment import (
    Button,
    Card,
    Drawer,
    Heading,
    Modal,
    Region,
    Surface,
    Tabs,
    Text,
    Toolbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_card_body_only() -> None:
    r = FragmentRenderer()
    out = r.render(Card(body=Text("contents")))
    assert "dz-card" in out
    assert "dz-text" in out
    assert "dz-card__header" not in out


def test_render_card_with_all_slots() -> None:
    r = FragmentRenderer()
    out = r.render(Card(
        header=Heading("Title", level=3),
        body=Text("body"),
        footer=Text("foot"),
    ))
    assert "dz-card__header" in out
    assert "dz-card__body" in out
    assert "dz-card__footer" in out


def test_render_surface_with_header() -> None:
    r = FragmentRenderer()
    out = r.render(Surface(
        header=Heading("Tasks"),
        body=Text("content"),
    ))
    assert "dz-surface" in out
    assert "dz-surface__header" in out


def test_render_region_kind_class() -> None:
    r = FragmentRenderer()
    out = r.render(Region(kind="list", body=Text("rows")))
    assert "dz-region" in out
    assert "dz-region--kind-list" in out


def test_render_toolbar_with_actions() -> None:
    r = FragmentRenderer()
    out = r.render(Toolbar(
        label="Actions",
        actions=(Button(label="New", variant="primary"),),
    ))
    assert "dz-toolbar" in out
    assert "New" in out


def test_render_tabs() -> None:
    r = FragmentRenderer()
    out = r.render(Tabs(tabs=(("a", Text("A")), ("b", Text("B")))))
    assert "dz-tabs" in out
    assert out.count("dz-text") == 2


def test_render_drawer_side_class() -> None:
    r = FragmentRenderer()
    out = r.render(Drawer(body=Text("contents"), side="left"))
    assert "dz-drawer--side-left" in out


def test_render_modal_size_class() -> None:
    r = FragmentRenderer()
    out = r.render(Modal(body=Text("contents"), size="lg"))
    assert "dz-modal--size-lg" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_containers.py -v`
Expected: FAIL with `FragmentError: renderer has no emit for 'Card' yet` (or similar for whichever container appears first)

- [ ] **Step 3: Add container emitters to the renderer**

In the match block, insert (before the `case _:` default):

```python
            # Containers
            case Surface():
                return self._emit_surface(fragment, ctx)
            case Card():
                return self._emit_card(fragment, ctx)
            case Region():
                return self._emit_region(fragment, ctx)
            case Toolbar():
                return self._emit_toolbar(fragment, ctx)
            case Drawer():
                return self._emit_drawer(fragment, ctx)
            case Modal():
                return self._emit_modal(fragment, ctx)
            case Tabs():
                return self._emit_tabs(fragment, ctx)
```

Add the emit methods:

```python
    def _emit_card(self, c: Card, ctx: RenderContext) -> str:
        tokens = c.tokens if c.tokens is not None else ctx.tokens.card
        cls_parts = [
            "dz-card",
            f"dz-card--radius-{tokens.radius}",
            f"dz-card--border-{tokens.border}",
            f"dz-card--padding-{tokens.padding}",
            f"dz-card--shadow-{tokens.shadow}",
        ]
        cls = " ".join(cls_parts)
        parts = [f'<div class="{cls}">']
        if c.header is not None:
            parts.append(f'<div class="dz-card__header">{self._emit(c.header, ctx)}</div>')
        parts.append(f'<div class="dz-card__body">{self._emit(c.body, ctx)}</div>')
        if c.footer is not None:
            parts.append(f'<div class="dz-card__footer">{self._emit(c.footer, ctx)}</div>')
        parts.append("</div>")
        return "".join(parts)

    def _emit_surface(self, s: Surface, ctx: RenderContext) -> str:
        parts = ['<section class="dz-surface">']
        if s.header is not None:
            parts.append(f'<header class="dz-surface__header">{self._emit(s.header, ctx)}</header>')
        parts.append(f'<div class="dz-surface__body">{self._emit(s.body, ctx)}</div>')
        if s.footer is not None:
            parts.append(f'<footer class="dz-surface__footer">{self._emit(s.footer, ctx)}</footer>')
        parts.append("</section>")
        return "".join(parts)

    def _emit_region(self, r: Region, ctx: RenderContext) -> str:
        cls = f"dz-region dz-region--kind-{r.kind}"
        return f'<section class="{cls}">{self._emit(r.body, ctx)}</section>'

    def _emit_toolbar(self, t: Toolbar, ctx: RenderContext) -> str:
        actions_html = "".join(self._emit(a, ctx) for a in t.actions)
        label = ctx.escape(t.label)
        return (
            f'<div class="dz-toolbar" aria-label="{label}">'
            f'{actions_html}'
            f'</div>'
        )

    def _emit_drawer(self, d: Drawer, ctx: RenderContext) -> str:
        cls = f"dz-drawer dz-drawer--side-{d.side}"
        return f'<aside class="{cls}">{self._emit(d.body, ctx)}</aside>'

    def _emit_modal(self, m: Modal, ctx: RenderContext) -> str:
        cls = f"dz-modal dz-modal--size-{m.size}"
        return f'<div class="{cls}" role="dialog">{self._emit(m.body, ctx)}</div>'

    def _emit_tabs(self, t: Tabs, ctx: RenderContext) -> str:
        tab_buttons = "".join(
            f'<button class="dz-tabs__button" data-tab="{ctx.escape(key)}">{ctx.escape(key)}</button>'
            for key, _panel in t.tabs
        )
        panels = "".join(
            f'<div class="dz-tabs__panel" data-tab="{ctx.escape(key)}">{self._emit(panel, ctx)}</div>'
            for key, panel in t.tabs
        )
        return f'<div class="dz-tabs"><div class="dz-tabs__buttons">{tab_buttons}</div>{panels}</div>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_containers.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_containers.py
git commit -m "feat(render): renderer support for Surface, Card, Region, Toolbar, Tabs, Drawer, Modal"
```

---

### Task 20: Render content primitives (Icon, Badge, EmptyState, Skeleton)

Text and Heading are already done in Task 17. Add the remaining content primitives.

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_content.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_content.py
from dazzle.render.fragment import (
    Badge,
    Button,
    EmptyState,
    Icon,
    Skeleton,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_icon() -> None:
    r = FragmentRenderer()
    out = r.render(Icon(name="check"))
    assert 'data-icon="check"' in out
    assert "dz-icon--size-md" in out


def test_render_badge() -> None:
    r = FragmentRenderer()
    out = r.render(Badge(label="new", variant="success"))
    assert "new" in out
    assert "dz-badge--variant-success" in out


def test_render_empty_state() -> None:
    r = FragmentRenderer()
    out = r.render(EmptyState(title="Nothing here", description="Add an item"))
    assert "Nothing here" in out
    assert "Add an item" in out


def test_render_empty_state_with_action() -> None:
    r = FragmentRenderer()
    out = r.render(EmptyState(
        title="Empty",
        description="Add one",
        action=Button(label="Create", variant="primary"),
    ))
    assert "Create" in out


def test_render_skeleton_lines() -> None:
    r = FragmentRenderer()
    out = r.render(Skeleton(lines=4))
    assert out.count("dz-skeleton__line") == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_content.py -v`
Expected: FAIL with `FragmentError: renderer has no emit for 'Icon' yet`

- [ ] **Step 3: Add content emitters**

Insert match arms in `_emit` (before `case _:`):

```python
            # Content (Text and Heading already in Task 17)
            case Icon():
                return self._emit_icon(fragment, ctx)
            case Badge():
                return self._emit_badge(fragment, ctx)
            case EmptyState():
                return self._emit_empty_state(fragment, ctx)
            case Skeleton():
                return self._emit_skeleton(fragment, ctx)
```

Add the emit methods:

```python
    def _emit_icon(self, i: Icon, ctx: RenderContext) -> str:
        name = ctx.escape(i.name)
        cls = f"dz-icon dz-icon--size-{i.size}"
        return f'<span class="{cls}" data-icon="{name}" aria-hidden="true"></span>'

    def _emit_badge(self, b: Badge, ctx: RenderContext) -> str:
        cls = f"dz-badge dz-badge--variant-{b.variant}"
        return f'<span class="{cls}">{ctx.escape(b.label)}</span>'

    def _emit_empty_state(self, e: EmptyState, ctx: RenderContext) -> str:
        action_html = self._emit(e.action, ctx) if e.action is not None else ""
        return (
            f'<div class="dz-empty-state">'
            f'<h3 class="dz-empty-state__title">{ctx.escape(e.title)}</h3>'
            f'<p class="dz-empty-state__description">{ctx.escape(e.description)}</p>'
            f'<div class="dz-empty-state__action">{action_html}</div>'
            f'</div>'
        )

    def _emit_skeleton(self, s: Skeleton, ctx: RenderContext) -> str:
        lines = "".join(
            '<div class="dz-skeleton__line"></div>' for _ in range(s.lines)
        )
        return f'<div class="dz-skeleton">{lines}</div>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_content.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_content.py
git commit -m "feat(render): renderer support for Icon, Badge, EmptyState, Skeleton"
```

---

### Task 21: Render interactive primitives (Button, Link, Interactive, InlineEdit) with htmx attributes

This task is the load-bearing htmx emission test. The post-init validators on Button (Task 12) ensure the inputs are coherent; this task verifies the renderer emits them as htmx-recognised attributes.

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_interactive.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_interactive.py
from dazzle.render.fragment import (
    URL,
    Button,
    HxTrigger,
    InlineEdit,
    Interactive,
    Link,
    TargetSelector,
    Text,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_button_label() -> None:
    r = FragmentRenderer()
    out = r.render(Button(label="Save", variant="primary"))
    assert "Save" in out
    assert "dz-button--variant-primary" in out


def test_render_button_with_htmx_get() -> None:
    r = FragmentRenderer()
    btn = Button(
        label="Refresh",
        hx_get=URL("/refresh"),
        hx_target=TargetSelector("#region-task_list-main"),
        hx_swap="innerHTML",
    )
    out = r.render(btn)
    assert 'hx-get="/refresh"' in out
    assert 'hx-target="#region-task_list-main"' in out
    assert 'hx-swap="innerHTML"' in out


def test_render_button_with_htmx_post_and_confirm() -> None:
    r = FragmentRenderer()
    btn = Button(
        label="Delete",
        variant="danger",
        hx_post=URL("/tasks/42/delete"),
        hx_target=TargetSelector("closest tr"),
        hx_swap="delete",
        hx_confirm="Are you sure?",
    )
    out = r.render(btn)
    assert 'hx-post="/tasks/42/delete"' in out
    assert 'hx-confirm="Are you sure?"' in out


def test_render_button_visibility_hidden_class() -> None:
    r = FragmentRenderer()
    out = r.render(Button(label="Maybe", visibility="hidden"))
    assert "dz-button--visibility-hidden" in out


def test_render_button_no_htmx_no_hx_attrs() -> None:
    """A button without htmx fields must not emit hx-* attributes."""
    r = FragmentRenderer()
    out = r.render(Button(label="Plain"))
    assert "hx-" not in out


def test_render_link() -> None:
    r = FragmentRenderer()
    out = r.render(Link(label="Open", href=URL("/items/42")))
    assert 'href="/items/42"' in out
    assert "Open" in out


def test_render_interactive_wrapper() -> None:
    r = FragmentRenderer()
    iw = Interactive(
        child=Text("clickable area"),
        hx_get=URL("/details/42"),
        hx_target=TargetSelector("#detail-pane"),
        hx_trigger=HxTrigger("click"),
    )
    out = r.render(iw)
    assert 'hx-get="/details/42"' in out
    assert 'hx-trigger="click"' in out
    assert "clickable area" in out


def test_render_inline_edit() -> None:
    r = FragmentRenderer()
    out = r.render(InlineEdit(field_name="title", value="Original", placeholder="Enter title"))
    assert "Original" in out
    assert 'data-field="title"' in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_interactive.py -v`
Expected: FAIL with `FragmentError: renderer has no emit for 'Button' yet`

- [ ] **Step 3: Add interactive emitters**

Insert match arms in `_emit`:

```python
            # Interactive
            case Button():
                return self._emit_button(fragment, ctx)
            case Link():
                return self._emit_link(fragment, ctx)
            case Interactive():
                return self._emit_interactive(fragment, ctx)
            case InlineEdit():
                return self._emit_inline_edit(fragment, ctx)
```

Add a private helper for htmx attribute emission and the per-primitive emit methods. The htmx helper centralises the attribute-name formatting so a future change (e.g. adding `hx-vals`) lives in one place:

```python
    @staticmethod
    def _hx_attrs(
        *,
        hx_get: object,
        hx_post: object,
        hx_target: object,
        hx_swap: object | None,
        hx_trigger: object | None = None,
        hx_indicator: object | None = None,
        hx_confirm: object | None = None,
    ) -> str:
        """Build the htmx attribute string for an interactive primitive.

        All values are stringified via __str__ which is the contract on the
        wrapper types (URL, TargetSelector, HxTrigger). hx-confirm is the
        only field that takes a free-form string."""
        parts: list[str] = []
        if hx_get is not None:
            parts.append(f'hx-get="{hx_get}"')
        if hx_post is not None:
            parts.append(f'hx-post="{hx_post}"')
        if hx_target is not None:
            parts.append(f'hx-target="{hx_target}"')
        if hx_swap is not None:
            parts.append(f'hx-swap="{hx_swap}"')
        if hx_trigger is not None:
            parts.append(f'hx-trigger="{hx_trigger}"')
        if hx_indicator is not None:
            parts.append(f'hx-indicator="{hx_indicator}"')
        if hx_confirm is not None:
            # hx-confirm can contain user-facing text — must be HTML-escaped.
            from html import escape as _escape
            parts.append(f'hx-confirm="{_escape(str(hx_confirm), quote=True)}"')
        return " ".join(parts)

    def _emit_button(self, b: Button, ctx: RenderContext) -> str:
        cls_parts = [
            "dz-button",
            f"dz-button--variant-{b.variant}",
            f"dz-button--visibility-{b.visibility}",
        ]
        cls = " ".join(cls_parts)
        attrs = self._hx_attrs(
            hx_get=b.hx_get,
            hx_post=b.hx_post,
            hx_target=b.hx_target,
            hx_swap=b.hx_swap,
            hx_trigger=b.hx_trigger,
            hx_indicator=b.hx_indicator,
            hx_confirm=b.hx_confirm,
        )
        attr_str = f" {attrs}" if attrs else ""
        disabled = ' disabled="disabled"' if b.visibility == "disabled" else ""
        label = ctx.escape(b.label)
        return f'<button type="button" class="{cls}"{attr_str}{disabled}>{label}</button>'

    def _emit_link(self, link: Link, ctx: RenderContext) -> str:
        href = str(link.href)
        return f'<a class="dz-link" href="{href}">{ctx.escape(link.label)}</a>'

    def _emit_interactive(self, iw: Interactive, ctx: RenderContext) -> str:
        attrs = self._hx_attrs(
            hx_get=iw.hx_get,
            hx_post=iw.hx_post,
            hx_target=iw.hx_target,
            hx_swap=iw.hx_swap,
            hx_trigger=iw.hx_trigger,
        )
        attr_str = f" {attrs}" if attrs else ""
        child_html = self._emit(iw.child, ctx)
        return f'<div class="dz-interactive"{attr_str}>{child_html}</div>'

    def _emit_inline_edit(self, ie: InlineEdit, ctx: RenderContext) -> str:
        # InlineEdit value should be escaped — it's user-supplied content.
        # The placeholder is developer-supplied but escape anyway as a safety net.
        value = ctx.escape(ie.value)
        placeholder = ctx.escape(ie.placeholder)
        return (
            f'<span class="dz-inline-edit" data-field="{ctx.escape(ie.field_name)}" '
            f'data-placeholder="{placeholder}">{value}</span>'
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_interactive.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_interactive.py
git commit -m "feat(render): renderer support for Button, Link, Interactive, InlineEdit (with htmx)"
```

---

### Task 22: Render data primitives (Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard, CalendarGrid)

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_data.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_data.py
from dazzle.render.fragment import (
    BarChart,
    CalendarGrid,
    KanbanBoard,
    KPI,
    PivotTable,
    Table,
    Text,
    Timeline,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_table() -> None:
    r = FragmentRenderer()
    t = Table(
        columns=("title", "status"),
        rows=(("Buy milk", "open"), ("Walk dog", "done")),
    )
    out = r.render(t)
    assert "<table" in out
    assert "Buy milk" in out
    assert "Walk dog" in out
    assert out.count("<tr") >= 3  # 1 header + 2 body rows
    assert "dz-table" in out


def test_render_table_escapes_cells() -> None:
    r = FragmentRenderer()
    t = Table(columns=("name",), rows=(("<script>",),))
    out = r.render(t)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_kpi() -> None:
    r = FragmentRenderer()
    out = r.render(KPI(label="Revenue", value="$42k", trend="up", delta="+12%"))
    assert "Revenue" in out
    assert "$42k" in out
    assert "dz-kpi--trend-up" in out


def test_render_bar_chart() -> None:
    r = FragmentRenderer()
    out = r.render(BarChart(label="By status", buckets=(("open", 3), ("done", 7))))
    assert "open" in out
    assert "3" in out


def test_render_pivot_table() -> None:
    r = FragmentRenderer()
    p = PivotTable(
        label="System x severity",
        rows=("auth",),
        columns=("low", "high"),
        cells={("auth", "low"): 1, ("auth", "high"): 2},
    )
    out = r.render(p)
    assert "<table" in out
    assert "auth" in out


def test_render_timeline() -> None:
    r = FragmentRenderer()
    out = r.render(Timeline(events=(("created", "2026-05-05"), ("updated", "2026-05-06"))))
    assert "created" in out
    assert "2026-05-05" in out


def test_render_kanban_board() -> None:
    r = FragmentRenderer()
    k = KanbanBoard(columns=(("open", (Text("a"), Text("b"))), ("done", ())))
    out = r.render(k)
    assert "dz-kanban" in out
    assert out.count("dz-kanban__column") == 2


def test_render_calendar_view_class() -> None:
    r = FragmentRenderer()
    out = r.render(CalendarGrid(view="week"))
    assert "dz-calendar--view-week" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_data.py -v`
Expected: FAIL with `FragmentError: renderer has no emit for 'Table' yet`

- [ ] **Step 3: Add data emitters**

Insert match arms in `_emit`:

```python
            # Data
            case Table():
                return self._emit_table(fragment, ctx)
            case KPI():
                return self._emit_kpi(fragment, ctx)
            case BarChart():
                return self._emit_bar_chart(fragment, ctx)
            case PivotTable():
                return self._emit_pivot_table(fragment, ctx)
            case Timeline():
                return self._emit_timeline(fragment, ctx)
            case KanbanBoard():
                return self._emit_kanban_board(fragment, ctx)
            case CalendarGrid():
                return self._emit_calendar_grid(fragment, ctx)
```

Add the emit methods:

```python
    def _emit_table(self, t: Table, ctx: RenderContext) -> str:
        head_cells = "".join(f'<th>{ctx.escape(c)}</th>' for c in t.columns)
        body_rows = "".join(
            "<tr>" + "".join(f'<td>{ctx.escape(cell)}</td>' for cell in row) + "</tr>"
            for row in t.rows
        )
        return (
            f'<table class="dz-table">'
            f'<thead><tr>{head_cells}</tr></thead>'
            f'<tbody>{body_rows}</tbody>'
            f'</table>'
        )

    def _emit_kpi(self, k: KPI, ctx: RenderContext) -> str:
        cls = f"dz-kpi dz-kpi--trend-{k.trend}"
        delta_html = f'<span class="dz-kpi__delta">{ctx.escape(k.delta)}</span>' if k.delta else ""
        return (
            f'<div class="{cls}">'
            f'<div class="dz-kpi__label">{ctx.escape(k.label)}</div>'
            f'<div class="dz-kpi__value">{ctx.escape(k.value)}</div>'
            f'{delta_html}'
            f'</div>'
        )

    def _emit_bar_chart(self, b: BarChart, ctx: RenderContext) -> str:
        bars = "".join(
            f'<div class="dz-bar-chart__bar" data-label="{ctx.escape(label)}">'
            f'<span class="dz-bar-chart__label">{ctx.escape(label)}</span>'
            f'<span class="dz-bar-chart__value">{count}</span>'
            f'</div>'
            for label, count in b.buckets
        )
        return (
            f'<div class="dz-bar-chart">'
            f'<div class="dz-bar-chart__title">{ctx.escape(b.label)}</div>'
            f'<div class="dz-bar-chart__bars">{bars}</div>'
            f'</div>'
        )

    def _emit_pivot_table(self, p: PivotTable, ctx: RenderContext) -> str:
        head = "".join(f'<th>{ctx.escape(c)}</th>' for c in p.columns)
        body = "".join(
            "<tr>"
            + f'<th>{ctx.escape(row)}</th>'
            + "".join(f'<td>{p.cells.get((row, col), 0)}</td>' for col in p.columns)
            + "</tr>"
            for row in p.rows
        )
        return (
            f'<table class="dz-pivot-table">'
            f'<caption>{ctx.escape(p.label)}</caption>'
            f'<thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{body}</tbody>'
            f'</table>'
        )

    def _emit_timeline(self, t: Timeline, ctx: RenderContext) -> str:
        events = "".join(
            f'<li class="dz-timeline__event">'
            f'<time datetime="{ctx.escape(when)}">{ctx.escape(when)}</time>'
            f'<span class="dz-timeline__label">{ctx.escape(label)}</span>'
            f'</li>'
            for label, when in t.events
        )
        return f'<ol class="dz-timeline">{events}</ol>'

    def _emit_kanban_board(self, k: KanbanBoard, ctx: RenderContext) -> str:
        cols = "".join(
            f'<div class="dz-kanban__column" data-key="{ctx.escape(key)}">'
            + "".join(self._emit(item, ctx) for item in items)
            + '</div>'
            for key, items in k.columns
        )
        return f'<div class="dz-kanban">{cols}</div>'

    def _emit_calendar_grid(self, c: CalendarGrid, ctx: RenderContext) -> str:
        cls = f"dz-calendar dz-calendar--view-{c.view}"
        events = "".join(
            f'<li class="dz-calendar__event">'
            f'<time datetime="{ctx.escape(when)}">{ctx.escape(when)}</time> '
            f'{ctx.escape(label)}'
            f'</li>'
            for label, when in c.events
        )
        return f'<div class="{cls}"><ul>{events}</ul></div>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_data.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_data.py
git commit -m "feat(render): renderer support for Table, KPI, BarChart, PivotTable, Timeline, KanbanBoard, CalendarGrid"
```

---

### Task 23: Render form primitives (FormStack, Field, Combobox, Submit)

**Files:**
- Modify: `src/dazzle/render/fragment/renderer.py`
- Create: `tests/unit/render/fragment/test_renderer_forms.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/render/fragment/test_renderer_forms.py
from dazzle.render.fragment import URL, Combobox, Field, FormStack, Submit
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_form_stack_action_method() -> None:
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/tasks/create"),
        fields=(Field(name="title", label="Title", required=True),),
    )
    out = r.render(fs)
    assert 'action="/tasks/create"' in out
    assert 'method="POST"' in out


def test_render_field_text() -> None:
    r = FragmentRenderer()
    out = r.render(Field(name="title", label="Title", required=True))
    assert 'name="title"' in out
    assert 'type="text"' in out
    assert "required" in out
    assert "Title" in out


def test_render_field_textarea() -> None:
    r = FragmentRenderer()
    out = r.render(Field(name="body", label="Body", kind="textarea"))
    assert "<textarea" in out


def test_render_combobox_options() -> None:
    r = FragmentRenderer()
    c = Combobox(
        name="status",
        label="Status",
        options=(("open", "Open"), ("closed", "Closed")),
    )
    out = r.render(c)
    assert "<select" in out
    assert 'value="open"' in out
    assert "Open" in out
    assert "Closed" in out


def test_render_submit_default_variant() -> None:
    r = FragmentRenderer()
    out = r.render(Submit(label="Save"))
    assert "Save" in out
    assert 'type="submit"' in out
    assert "dz-submit--variant-primary" in out


def test_render_form_stack_with_submit() -> None:
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/save"),
        fields=(Field(name="title", label="Title"),),
        submit=Submit(label="Save"),
    )
    out = r.render(fs)
    assert "Save" in out
    assert 'type="submit"' in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/render/fragment/test_renderer_forms.py -v`
Expected: FAIL with `FragmentError: renderer has no emit for 'FormStack' yet`

- [ ] **Step 3: Add form emitters**

Insert match arms in `_emit`:

```python
            # Forms
            case FormStack():
                return self._emit_form_stack(fragment, ctx)
            case Field():
                return self._emit_field(fragment, ctx)
            case Combobox():
                return self._emit_combobox(fragment, ctx)
            case Submit():
                return self._emit_submit(fragment, ctx)
```

Add the emit methods:

```python
    def _emit_form_stack(self, fs: FormStack, ctx: RenderContext) -> str:
        action = str(fs.action)
        fields_html = "".join(self._emit(f, ctx) for f in fs.fields)
        submit_html = self._emit(fs.submit, ctx) if fs.submit is not None else ""
        return (
            f'<form class="dz-form-stack" action="{action}" method="{fs.method}">'
            f'{fields_html}{submit_html}'
            f'</form>'
        )

    def _emit_field(self, f: Field, ctx: RenderContext) -> str:
        # Field labels are developer-supplied; values may be user-supplied —
        # escape both as a safety net.
        label = ctx.escape(f.label)
        name = ctx.escape(f.name)
        placeholder = ctx.escape(f.placeholder)
        initial = ctx.escape(f.initial_value)
        required_attr = " required" if f.required else ""

        if f.kind == "textarea":
            inner = (
                f'<textarea class="dz-field__input" name="{name}" '
                f'placeholder="{placeholder}"{required_attr}>{initial}</textarea>'
            )
        elif f.kind == "checkbox":
            checked = " checked" if f.initial_value == "true" else ""
            inner = (
                f'<input class="dz-field__input" type="checkbox" name="{name}"'
                f'{checked}{required_attr}>'
            )
        else:
            inner = (
                f'<input class="dz-field__input" type="{f.kind}" name="{name}" '
                f'value="{initial}" placeholder="{placeholder}"{required_attr}>'
            )
        return (
            f'<label class="dz-field">'
            f'<span class="dz-field__label">{label}</span>'
            f'{inner}'
            f'</label>'
        )

    def _emit_combobox(self, c: Combobox, ctx: RenderContext) -> str:
        options = "".join(
            f'<option value="{ctx.escape(value)}"'
            + (' selected' if value == c.initial_value else '')
            + f'>{ctx.escape(label)}</option>'
            for value, label in c.options
        )
        required_attr = " required" if c.required else ""
        label = ctx.escape(c.label)
        name = ctx.escape(c.name)
        return (
            f'<label class="dz-combobox">'
            f'<span class="dz-combobox__label">{label}</span>'
            f'<select class="dz-combobox__select" name="{name}"{required_attr}>{options}</select>'
            f'</label>'
        )

    def _emit_submit(self, s: Submit, ctx: RenderContext) -> str:
        cls = f"dz-submit dz-submit--variant-{s.variant}"
        return f'<button type="submit" class="{cls}">{ctx.escape(s.label)}</button>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/render/fragment/test_renderer_forms.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/render/fragment/renderer.py tests/unit/render/fragment/test_renderer_forms.py
git commit -m "feat(render): renderer support for FormStack, Field, Combobox, Submit"
```

---

### Task 24: Fragment exhaustiveness + HTML5 validity property tests

These two tests are the cumulative gates that prove Phase 3 is complete.

- The exhaustiveness test instantiates every primitive in the `Fragment` union and renders it; if a new primitive is added without a renderer match arm, this test fails.
- The HTML5 validity test parses the rendered output and confirms it parses as well-formed HTML5.

**Files:**
- Create: `tests/unit/render/fragment/test_fragment_exhaustiveness.py`
- Create: `tests/unit/render/fragment/test_html5_validity.py`

- [ ] **Step 1: Write the exhaustiveness test**

```python
# tests/unit/render/fragment/test_fragment_exhaustiveness.py
"""Construct one of every primitive in the Fragment union and render each.

Adding a new primitive without adding a renderer match arm makes this test
fail with FragmentError. This is the runtime exhaustiveness check that
complements mypy's static one."""

import typing

from dazzle.render.fragment import (
    URL,
    BarChart,
    Badge,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    Drawer,
    EmptyState,
    Field,
    FormStack,
    Fragment,
    Grid,
    Heading,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    KPI,
    Link,
    Modal,
    PivotTable,
    RawHTML,
    Region,
    Row,
    Skeleton,
    Slot,
    Split,
    Stack,
    Submit,
    Surface,
    Table,
    Tabs,
    TargetSelector,
    Text,
    Timeline,
    Toolbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _sample_for(primitive_type: type) -> object:
    """Return a constructed instance of `primitive_type` with safe defaults.

    Adding a new primitive means adding a sample here. The match-style
    if/elif chain is intentional: it keeps the sample-construction logic
    co-located with the type and visible in diffs."""
    if primitive_type is Stack:
        return Stack(children=(Text("a"),))
    if primitive_type is Row:
        return Row(children=(Text("a"),))
    if primitive_type is Split:
        return Split(start=Text("L"), end=Text("R"))
    if primitive_type is Grid:
        return Grid(children=(Text("a"),))
    if primitive_type is Surface:
        return Surface(body=Text("body"))
    if primitive_type is Card:
        return Card(body=Text("body"))
    if primitive_type is Region:
        return Region(kind="list", body=Text("body"))
    if primitive_type is Toolbar:
        return Toolbar(label="actions")
    if primitive_type is Drawer:
        return Drawer(body=Text("body"))
    if primitive_type is Modal:
        return Modal(body=Text("body"))
    if primitive_type is Tabs:
        return Tabs(tabs=(("a", Text("A")),))
    if primitive_type is Text:
        return Text("hello")
    if primitive_type is Heading:
        return Heading("title")
    if primitive_type is Icon:
        return Icon(name="check")
    if primitive_type is Badge:
        return Badge(label="new")
    if primitive_type is EmptyState:
        return EmptyState(title="t", description="d")
    if primitive_type is Skeleton:
        return Skeleton()
    if primitive_type is Button:
        return Button(label="ok")
    if primitive_type is Link:
        return Link(label="open", href=URL("/x"))
    if primitive_type is InlineEdit:
        return InlineEdit(field_name="title", value="v")
    if primitive_type is Interactive:
        return Interactive(
            child=Text("c"),
            hx_get=URL("/x"),
            hx_target=TargetSelector("#t"),
        )
    if primitive_type is Table:
        return Table(columns=("a",), rows=(("v",),))
    if primitive_type is KanbanBoard:
        return KanbanBoard(columns=(("col", ()),))
    if primitive_type is CalendarGrid:
        return CalendarGrid()
    if primitive_type is Timeline:
        return Timeline(events=(("e", "2026-01-01"),))
    if primitive_type is KPI:
        return KPI(label="rev", value="1")
    if primitive_type is BarChart:
        return BarChart(label="x", buckets=(("a", 1),))
    if primitive_type is PivotTable:
        return PivotTable(
            label="x",
            rows=("r",),
            columns=("c",),
            cells={("r", "c"): 0},
        )
    if primitive_type is FormStack:
        return FormStack(action=URL("/x"), fields=(Field(name="t", label="T"),))
    if primitive_type is Field:
        return Field(name="t", label="T")
    if primitive_type is Combobox:
        return Combobox(name="s", label="S", options=(("a", "A"),))
    if primitive_type is Submit:
        return Submit(label="Save")
    if primitive_type is RawHTML:
        return RawHTML("<span>raw</span>")
    if primitive_type is Slot:
        # Slot is special-cased below — it raises at render time.
        return Slot(name="s")
    raise AssertionError(f"no sample defined for {primitive_type!r}")


def test_every_primitive_in_fragment_alias_is_renderable() -> None:
    r = FragmentRenderer()
    for ptype in typing.get_args(Fragment):
        sample = _sample_for(ptype)
        if isinstance(sample, Slot):
            # Slot deliberately raises at render time (Task 17). Verify that.
            import pytest as _pytest
            with _pytest.raises(Exception, match="unfilled slot"):
                r.render(sample)
            continue
        out = r.render(sample)
        assert isinstance(out, str)
        assert out, f"{ptype.__name__} rendered to empty string"
```

- [ ] **Step 2: Write the HTML5 validity test**

```python
# tests/unit/render/fragment/test_html5_validity.py
"""Property test: every primitive emits HTML that parses without errors.

Uses html.parser (stdlib) — strict-but-not-comprehensive. Catches obvious
unclosed tags and malformed attributes. A future enhancement could plug in
html5lib for stricter parsing."""

from html.parser import HTMLParser

import pytest

from dazzle.render.fragment import Fragment
from dazzle.render.fragment.renderer import FragmentRenderer
from tests.unit.render.fragment.test_fragment_exhaustiveness import _sample_for


class _Validator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void elements per HTML5 — don't push onto stack
        if tag not in {"input", "br", "hr", "img", "meta", "link"}:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.open_tags:
            self.errors.append(f"unexpected </{tag}> with no open tag")
            return
        if self.open_tags[-1] != tag:
            self.errors.append(
                f"close mismatch: expected </{self.open_tags[-1]}>, got </{tag}>"
            )
        self.open_tags.pop()

    def error(self, message: str) -> None:  # type: ignore[override]
        self.errors.append(message)


import typing


def _all_primitive_types() -> list[type]:
    return list(typing.get_args(Fragment))


@pytest.mark.parametrize("ptype", _all_primitive_types(), ids=lambda t: t.__name__)
def test_primitive_emits_well_formed_html(ptype: type) -> None:
    from dazzle.render.fragment import Slot
    r = FragmentRenderer()
    sample = _sample_for(ptype)
    if isinstance(sample, Slot):
        pytest.skip("Slot raises at render time by design")

    html = r.render(sample)

    parser = _Validator()
    parser.feed(html)
    parser.close()

    if parser.open_tags:
        parser.errors.append(f"unclosed tags: {parser.open_tags}")
    assert not parser.errors, (
        f"{ptype.__name__} produced malformed HTML:\n"
        f"errors: {parser.errors}\n"
        f"output: {html!r}"
    )
```

- [ ] **Step 3: Run both tests**

Run: `pytest tests/unit/render/fragment/test_fragment_exhaustiveness.py tests/unit/render/fragment/test_html5_validity.py -v`

Expected: PASS for both. The exhaustiveness test: 1 test that touches every Fragment member. The validity test: parametrised, one parametrised case per primitive type — ~33 parametrised passes.

If anything FAILs:
- Exhaustiveness failure → check `_emit` for a missing match arm.
- Validity failure → look at the errors and the output; usually an unclosed tag in an emit method or a missing escape.

- [ ] **Step 4: Run the full render test suite**

Run: `pytest tests/unit/render/ -v`
Expected: PASS — every test in the render suite. ~95+ cumulative tests.

- [ ] **Step 5: Run mypy on the package**

Run: `mypy src/dazzle/render --strict`
Expected: `Success: no issues found in N source files`

- [ ] **Step 6: Run ruff**

Run: `ruff check src/dazzle/render tests/unit/render --fix && ruff format src/dazzle/render tests/unit/render`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/render/fragment/test_fragment_exhaustiveness.py tests/unit/render/fragment/test_html5_validity.py
git commit -m "test(render): exhaustiveness + html5 validity property tests"
```

---

## Plan completion checklist

After Task 24 is committed:

- [ ] Run `pytest tests/unit/render/ -v` — all tests pass.
- [ ] Run `pytest tests/ -m "not e2e"` — full unit suite still passes (no regressions outside the render package).
- [ ] Run `mypy src/dazzle/render --strict` — clean.
- [ ] Run `mypy src/dazzle --ignore-missing-imports` — no new errors elsewhere.
- [ ] Run `ruff check src/dazzle tests/ && ruff format --check src/dazzle tests/` — clean.
- [ ] Confirm `src/dazzle/render/` is a leaf package: `grep -r "from dazzle_http\|from dazzle_page\|from dazzle.core.ir" src/dazzle/render/` should return nothing. The render package must not import from those modules; integration happens in Plan 2.
- [ ] Confirm `dazzle serve` on `examples/simple_task` still works unchanged — the new package is import-only and does not affect serving.

When all green: ship per `/ship`. End state — the typed Fragment library exists, is fully tested, can construct and render every framework primitive to valid HTML, and is completely isolated from Dazzle's serving path. Plan 2 wires it up.

---

## Self-Review

**Spec coverage:**
- Spec §1 (Fragment type catalogue) → Tasks 9–16 (primitives) + Task 17 (renderer skeleton) cover it.
- Spec §2 (frozen dataclasses, not Pydantic) → enforced throughout; the `--strict` mypy gate in Task 24 catches accidental Pydantic intrusions.
- Spec §3 (renderer dispatch and `render:` DSL) → out of scope (Plan 2). Plan calls this out in the header.
- Spec §4 (Jinja interop) → out of scope (Plan 2/3). Plan calls this out.
- Spec §5 (primitive registration API) → Task 8 builds the registry; Plan 2 wires it into `RuntimeServices`.
- Spec §6 (token integration) → Task 4 (token types), Task 19 (Card consumes tokens). Sheet-loading from named theme is Plan 2.
- Spec §7 (htmx integration) → Task 6 (wrapper types), Task 12 (typed fields, post-init validators), Task 21 (renderer emits attributes).
- Spec §8 (anti-Turing boundary) → enforced structurally throughout; nothing in this package uses `eval`, `exec`, or runtime metaprogramming beyond dataclass introspection.

**Placeholder scan:**
- No "TBD"/"TODO"/"implement later" anywhere in this plan.
- Every step contains complete code — no "similar to Task N" shortcuts.
- All file paths are exact.
- Type names referenced in later tasks (`Button`, `Toolbar`, `Fragment`) are defined in earlier tasks.

**Type consistency:**
- `Fragment` declared in Task 16 — used in Task 17+ via the `_emit(fragment: Fragment, ...)` signature.
- `URL`, `TargetSelector`, `HxTrigger` declared in Task 6 — used in Tasks 12 and 21.
- `RenderContext` declared in Task 5 — used in every renderer task.
- `CardTokens`/`ButtonTokens` declared in Task 4 — used in Task 19 (Card emit) and Task 21 (Button accepts tokens).
- The `_validate_htmx_pair` helper is defined in Task 12 and used by both Button and Interactive in the same task.
- Layout/container/data primitive types use `tuple[object, ...]` for children/body fields (acknowledged in Task 9 doctstring as a forward-reference workaround); the `Fragment` alias is established in Task 16 but never threaded back into the primitive field types because doing so would create the same circular import the workaround sidesteps. The runtime exhaustiveness test (Task 24) catches the case mypy can't.

**Scope check:**
- Plan covers Phases 0–3 of the spec. Self-contained: end state is a working, tested library that does not affect serving. Plans 2 and 3 are their own units of work.
