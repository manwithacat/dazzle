# UX Component Expansion — Phase 2: Server-Driven Components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire DaisyUI CSS components and HTMX-native patterns into Dazzle's template layer — toasts, modals, breadcrumbs, accordion, skeleton loaders, alert banners, steps indicator, and lazy-loaded sections.

**Architecture:** New Jinja2 fragments in `templates/fragments/` and one component in `templates/components/`. Server-side `breadcrumbs.py` module for route-to-breadcrumb derivation. All patterns use existing DaisyUI classes + HTMX attributes from Phase 1 extensions. No new JS dependencies.

**Tech Stack:** Jinja2, DaisyUI v4 CSS classes, HTMX (remove-me, class-tools), FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-28-ux-component-expansion-design.md` (Phase 2 section)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_ui/templates/fragments/toast.html` | Create | Auto-dismissing toast fragment |
| `src/dazzle_ui/templates/fragments/alert_banner.html` | Create | Full-width alert/banner |
| `src/dazzle_ui/templates/fragments/breadcrumbs.html` | Create | Breadcrumb trail |
| `src/dazzle_ui/templates/fragments/steps_indicator.html` | Create | Visual stepper |
| `src/dazzle_ui/templates/fragments/accordion.html` | Create | Collapsible sections with optional lazy-load |
| `src/dazzle_ui/templates/fragments/skeleton_patterns.html` | Create | Skeleton presets (table row, card, detail) |
| `src/dazzle_ui/templates/components/modal.html` | Create | General-purpose server-loaded modal |
| `src/dazzle_back/runtime/breadcrumbs.py` | Create | Route-to-breadcrumb derivation |
| `tests/unit/test_breadcrumbs.py` | Create | Breadcrumb derivation tests |
| `tests/unit/test_phase2_fragments.py` | Create | Template rendering tests for all new fragments |

---

### Task 1: Toast Fragment

**Files:**
- Create: `src/dazzle_ui/templates/fragments/toast.html`

- [ ] **Step 1: Create the toast fragment**

```html
{# Auto-dismissing toast notification — used by with_toast() response helper #}
{# Parameters: message (str), level (str: success|error|warning|info, default: info) #}
{% set level = level | default('info') %}
<div class="alert alert-{{ level }}" remove-me="5s" role="alert">
  <span>{{ message }}</span>
</div>
```

This fragment is rendered server-side by `with_toast()` from `response_helpers.py`. It uses the `remove-me` HTMX extension from Phase 1 for auto-dismissal. The fragment itself is simple because the response helper handles the OOB swap wrapper.

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/fragments/toast.html
git commit -m "feat(ui): add toast fragment with remove-me auto-dismiss"
```

---

### Task 2: Alert Banner Fragment

**Files:**
- Create: `src/dazzle_ui/templates/fragments/alert_banner.html`

- [ ] **Step 1: Create the alert banner fragment**

```html
{# Full-width alert banner — for page-level messages #}
{# Parameters: message (str), level (str: success|error|warning|info), dismissible (bool, default: true), icon (str, optional) #}
{% set level = level | default('info') %}
{% set dismissible = dismissible | default(true) %}
<div class="alert alert-{{ level }} rounded-none" role="alert"
     {% if dismissible %}x-data="{ show: true }" x-show="show" x-transition{% endif %}>
  {% if icon %}
  <i data-lucide="{{ icon }}" class="w-5 h-5"></i>
  {% endif %}
  <span>{{ message }}</span>
  {% if dismissible %}
  <button @click="show = false" class="btn btn-ghost btn-sm btn-circle" aria-label="Dismiss">&times;</button>
  {% endif %}
</div>
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/fragments/alert_banner.html
git commit -m "feat(ui): add alert banner fragment with dismissible support"
```

---

### Task 3: Breadcrumbs Fragment + Server Module

**Files:**
- Create: `src/dazzle_ui/templates/fragments/breadcrumbs.html`
- Create: `src/dazzle_back/runtime/breadcrumbs.py`
- Create: `tests/unit/test_breadcrumbs.py`

- [ ] **Step 1: Write breadcrumb tests**

```python
# tests/unit/test_breadcrumbs.py
"""Tests for breadcrumb trail derivation."""

from dazzle_back.runtime.breadcrumbs import Crumb, build_breadcrumb_trail


class TestBuildBreadcrumbTrail:
    def test_root_path_returns_home_only(self):
        trail = build_breadcrumb_trail("/", {})
        assert len(trail) == 1
        assert trail[0].label == "Home"
        assert trail[0].url == "/"

    def test_single_segment(self):
        trail = build_breadcrumb_trail("/tasks", {})
        assert len(trail) == 2
        assert trail[0].label == "Home"
        assert trail[1].label == "Tasks"
        assert trail[1].url == "/tasks"

    def test_multi_segment(self):
        trail = build_breadcrumb_trail("/tasks/123/comments", {})
        assert len(trail) == 4
        assert trail[0].label == "Home"
        assert trail[1].label == "Tasks"
        assert trail[2].label == "123"
        assert trail[3].label == "Comments"

    def test_label_overrides(self):
        overrides = {"/tasks": "My Tasks", "/tasks/123": "Fix Bug #42"}
        trail = build_breadcrumb_trail("/tasks/123", overrides)
        assert trail[1].label == "My Tasks"
        assert trail[2].label == "Fix Bug #42"

    def test_last_crumb_has_no_url(self):
        trail = build_breadcrumb_trail("/tasks/123", {})
        assert trail[-1].url is None

    def test_empty_segments_stripped(self):
        trail = build_breadcrumb_trail("/tasks//123/", {})
        assert len(trail) == 3  # Home, Tasks, 123

    def test_crumb_dataclass_fields(self):
        crumb = Crumb(label="Test", url="/test")
        assert crumb.label == "Test"
        assert crumb.url == "/test"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_breadcrumbs.py -v
```

- [ ] **Step 3: Implement breadcrumbs module**

```python
# src/dazzle_back/runtime/breadcrumbs.py
"""
Breadcrumb trail derivation from URL paths.

Generates a list of Crumb objects from the current request path,
with optional label overrides for human-readable names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Crumb:
    """A single breadcrumb entry."""

    label: str
    url: str | None = None


def build_breadcrumb_trail(
    path: str,
    label_overrides: dict[str, str] | None = None,
) -> list[Crumb]:
    """Build a breadcrumb trail from a URL path.

    Args:
        path: The current request path (e.g., ``/tasks/123/comments``).
        label_overrides: Optional mapping of path prefixes to display labels.

    Returns:
        List of Crumb objects. The last crumb has ``url=None`` (current page).
    """
    overrides = label_overrides or {}
    segments = [s for s in path.strip("/").split("/") if s]

    crumbs: list[Crumb] = []

    if not segments:
        return [Crumb(label="Home", url="/")]

    crumbs.append(Crumb(label="Home", url="/"))

    for i, segment in enumerate(segments):
        accumulated = "/" + "/".join(segments[: i + 1])
        label = overrides.get(accumulated, segment.replace("-", " ").replace("_", " ").title())
        is_last = i == len(segments) - 1
        crumbs.append(Crumb(label=label, url=None if is_last else accumulated))

    return crumbs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_breadcrumbs.py -v
```

- [ ] **Step 5: Create breadcrumbs fragment**

```html
{# Breadcrumb navigation trail — DaisyUI breadcrumbs component #}
{# Parameters: crumbs (list of Crumb objects with .label and .url) #}
{% if crumbs and crumbs | length > 1 %}
<div class="breadcrumbs text-sm" aria-label="Breadcrumb">
  <ul>
    {% for crumb in crumbs %}
    <li>
      {% if crumb.url %}
      <a href="{{ crumb.url }}" hx-get="{{ crumb.url }}" hx-push-url="true" hx-target="body">{{ crumb.label }}</a>
      {% else %}
      <span aria-current="page">{{ crumb.label }}</span>
      {% endif %}
    </li>
    {% endfor %}
  </ul>
</div>
{% endif %}
```

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/dazzle_back/runtime/breadcrumbs.py tests/unit/test_breadcrumbs.py --fix
ruff format src/dazzle_back/runtime/breadcrumbs.py tests/unit/test_breadcrumbs.py
git add src/dazzle_ui/templates/fragments/breadcrumbs.html \
        src/dazzle_back/runtime/breadcrumbs.py \
        tests/unit/test_breadcrumbs.py
git commit -m "feat(ui): add breadcrumb fragment and server-side trail builder"
```

---

### Task 4: Steps Indicator Fragment

**Files:**
- Create: `src/dazzle_ui/templates/fragments/steps_indicator.html`

- [ ] **Step 1: Create the steps indicator fragment**

```html
{# Visual step indicator for multi-step flows — DaisyUI steps component #}
{# Parameters: steps (list of {label: str}), current_step (int, 1-based) #}
{% set current = current_step | default(1) %}
<ul class="steps w-full">
  {% for step in steps %}
  <li class="step{% if loop.index <= current %} step-primary{% endif %}"
      {% if loop.index == current %}aria-current="step"{% endif %}>
    {{ step.label }}
  </li>
  {% endfor %}
</ul>
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/fragments/steps_indicator.html
git commit -m "feat(ui): add steps indicator fragment for wizard flows"
```

---

### Task 5: Accordion Fragment

**Files:**
- Create: `src/dazzle_ui/templates/fragments/accordion.html`

- [ ] **Step 1: Create the accordion fragment**

```html
{# Accordion / collapsible sections — DaisyUI collapse with optional lazy-load #}
{# Parameters: sections (list of {id: str, title: str, content: str|None, endpoint: str|None}) #}
{# If endpoint is provided, content lazy-loads on first open via HTMX #}
{% for section in sections %}
<div class="collapse collapse-arrow bg-base-100 border border-base-300 {% if not loop.first %}mt-1{% endif %}"
     {% if section.endpoint %}x-collapse{% endif %}>
  {% if section.endpoint %}
  {# Lazy-loaded: fetch content on first open #}
  <details hx-get="{{ section.endpoint }}"
           hx-trigger="toggle once"
           hx-target="#accordion-content-{{ section.id }}"
           hx-swap="innerHTML">
    <summary class="collapse-title font-medium">{{ section.title }}</summary>
    <div class="collapse-content" id="accordion-content-{{ section.id }}">
      <span class="loading loading-dots loading-sm"></span>
    </div>
  </details>
  {% else %}
  {# Static content #}
  <details {% if loop.first %}open{% endif %}>
    <summary class="collapse-title font-medium">{{ section.title }}</summary>
    <div class="collapse-content">
      {{ section.content | safe }}
    </div>
  </details>
  {% endif %}
</div>
{% endfor %}
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/fragments/accordion.html
git commit -m "feat(ui): add accordion fragment with lazy-load support"
```

---

### Task 6: Skeleton Patterns Fragment

**Files:**
- Create: `src/dazzle_ui/templates/fragments/skeleton_patterns.html`

- [ ] **Step 1: Create skeleton patterns as Jinja2 macros**

```html
{# Skeleton loading patterns — DaisyUI skeleton component presets #}
{# Usage: {% from "fragments/skeleton_patterns.html" import skeleton_table_rows, skeleton_card, skeleton_detail %} #}

{% macro skeleton_table_rows(rows=5, cols=4) %}
{# Skeleton table body — shimmer rows for table loading state #}
{% for _ in range(rows) %}
<tr>
  {% for _ in range(cols) %}
  <td><div class="skeleton h-4 w-full"></div></td>
  {% endfor %}
</tr>
{% endfor %}
{% endmacro %}

{% macro skeleton_card() %}
{# Skeleton card — shimmer card for grid loading state #}
<div class="card bg-base-100 border border-base-300">
  <div class="card-body gap-3">
    <div class="skeleton h-4 w-3/4"></div>
    <div class="skeleton h-3 w-1/2"></div>
    <div class="skeleton h-3 w-full"></div>
    <div class="skeleton h-3 w-5/6"></div>
  </div>
</div>
{% endmacro %}

{% macro skeleton_detail() %}
{# Skeleton detail view — shimmer fields for detail loading state #}
<div class="space-y-4">
  <div class="skeleton h-6 w-1/3"></div>
  {% for _ in range(4) %}
  <div class="flex gap-4">
    <div class="skeleton h-4 w-24"></div>
    <div class="skeleton h-4 w-48"></div>
  </div>
  {% endfor %}
</div>
{% endmacro %}

{% macro skeleton_cards(count=6) %}
{# Grid of skeleton cards #}
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {% for _ in range(count) %}
  {{ skeleton_card() }}
  {% endfor %}
</div>
{% endmacro %}
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/fragments/skeleton_patterns.html
git commit -m "feat(ui): add skeleton pattern macros (table, card, detail)"
```

---

### Task 7: General-Purpose Modal Component

**Files:**
- Create: `src/dazzle_ui/templates/components/modal.html`

- [ ] **Step 1: Create the modal component**

```html
{# General-purpose server-loaded modal — uses native <dialog> element #}
{# Parameters: modal_id (str, default: 'dz-modal'), title (str), size (str: sm|md|lg|xl, default: md) #}
{# Usage: server returns this template via hx-get, then JS calls dialog.showModal() #}
{% set modal_id = modal_id | default('dz-modal') %}
{% set size = size | default('md') %}
{% set size_classes = {
  'sm': 'max-w-sm',
  'md': 'max-w-lg',
  'lg': 'max-w-2xl',
  'xl': 'max-w-4xl',
} %}
<dialog id="{{ modal_id }}" class="modal">
  <div class="modal-box {{ size_classes.get(size, 'max-w-lg') }}">
    {% if title %}
    <h3 class="text-lg font-bold">{{ title }}</h3>
    {% endif %}

    {# Close button #}
    <form method="dialog" class="absolute right-4 top-4">
      <button class="btn btn-ghost btn-sm btn-circle" aria-label="Close">&times;</button>
    </form>

    {# Content — caller fills this #}
    <div class="py-4">
      {% block modal_content %}
      {{ content | safe if content else '' }}
      {% endblock %}
    </div>

    {# Footer actions — optional #}
    {% if caller is defined %}
    <div class="modal-action">
      {{ caller() }}
    </div>
    {% endif %}
  </div>

  {# Backdrop click to close #}
  <form method="dialog" class="modal-backdrop">
    <button aria-label="Close">close</button>
  </form>
</dialog>
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle_ui/templates/components/modal.html
git commit -m "feat(ui): add general-purpose server-loaded modal component"
```

---

### Task 8: Fragment Rendering Tests

**Files:**
- Create: `tests/unit/test_phase2_fragments.py`

- [ ] **Step 1: Write rendering tests for all new fragments**

```python
# tests/unit/test_phase2_fragments.py
"""Tests for Phase 2 UI fragments — verify template rendering output."""

import pathlib

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402

TEMPLATE_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "templates"
)


@pytest.fixture
def jinja_env():
    return create_jinja_env()


class TestToastFragment:
    def test_renders_alert_with_level(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "fragments/toast.html" %}'
        )
        html = tmpl.render(message="Saved", level="success")
        assert "alert-success" in html
        assert "Saved" in html
        assert 'remove-me="5s"' in html

    def test_default_level_is_info(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "fragments/toast.html" %}'
        )
        html = tmpl.render(message="Hello")
        assert "alert-info" in html


class TestAlertBanner:
    def test_renders_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "fragments/alert_banner.html" %}'
        )
        html = tmpl.render(message="Warning!", level="warning")
        assert "alert-warning" in html
        assert "Warning!" in html
        assert 'x-data="{ show: true }"' in html
        assert "Dismiss" in html

    def test_non_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "fragments/alert_banner.html" %}'
        )
        html = tmpl.render(message="Info", level="info", dismissible=False)
        assert "alert-info" in html
        assert "x-data" not in html


class TestBreadcrumbs:
    def test_renders_breadcrumb_trail(self, jinja_env):
        from dazzle_back.runtime.breadcrumbs import Crumb

        crumbs = [
            Crumb(label="Home", url="/"),
            Crumb(label="Tasks", url="/tasks"),
            Crumb(label="Task 1", url=None),
        ]
        tmpl = jinja_env.from_string(
            '{% include "fragments/breadcrumbs.html" %}'
        )
        html = tmpl.render(crumbs=crumbs)
        assert "breadcrumbs" in html
        assert "Home" in html
        assert "Tasks" in html
        assert 'aria-current="page"' in html

    def test_single_crumb_hidden(self, jinja_env):
        from dazzle_back.runtime.breadcrumbs import Crumb

        crumbs = [Crumb(label="Home", url="/")]
        tmpl = jinja_env.from_string(
            '{% include "fragments/breadcrumbs.html" %}'
        )
        html = tmpl.render(crumbs=crumbs)
        assert html.strip() == ""


class TestStepsIndicator:
    def test_renders_steps(self, jinja_env):
        steps = [{"label": "Info"}, {"label": "Review"}, {"label": "Done"}]
        tmpl = jinja_env.from_string(
            '{% include "fragments/steps_indicator.html" %}'
        )
        html = tmpl.render(steps=steps, current_step=2)
        assert html.count("step-primary") == 2
        assert 'aria-current="step"' in html


class TestAccordion:
    def test_renders_static_sections(self, jinja_env):
        sections = [
            {"id": "a", "title": "Section A", "content": "<p>Content A</p>", "endpoint": None},
            {"id": "b", "title": "Section B", "content": "<p>Content B</p>", "endpoint": None},
        ]
        tmpl = jinja_env.from_string(
            '{% include "fragments/accordion.html" %}'
        )
        html = tmpl.render(sections=sections)
        assert "Section A" in html
        assert "Content A" in html
        assert "collapse-arrow" in html

    def test_lazy_load_section_has_htmx(self, jinja_env):
        sections = [
            {"id": "lazy", "title": "Lazy", "content": None, "endpoint": "/api/lazy"},
        ]
        tmpl = jinja_env.from_string(
            '{% include "fragments/accordion.html" %}'
        )
        html = tmpl.render(sections=sections)
        assert 'hx-get="/api/lazy"' in html
        assert 'hx-trigger="toggle once"' in html
        assert "loading loading-dots" in html


class TestSkeletonPatterns:
    def test_skeleton_table_rows(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% from "fragments/skeleton_patterns.html" import skeleton_table_rows %}'
            '{{ skeleton_table_rows(rows=3, cols=2) }}'
        )
        html = tmpl.render()
        assert html.count("<tr>") == 3
        assert html.count("skeleton") == 6

    def test_skeleton_card(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% from "fragments/skeleton_patterns.html" import skeleton_card %}'
            '{{ skeleton_card() }}'
        )
        html = tmpl.render()
        assert "skeleton" in html
        assert "card" in html


class TestModal:
    def test_renders_dialog(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "components/modal.html" %}'
        )
        html = tmpl.render(title="Edit Item", content="<form>Fields</form>")
        assert "<dialog" in html
        assert "Edit Item" in html
        assert "Fields" in html
        assert "modal-backdrop" in html

    def test_size_classes(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% include "components/modal.html" %}'
        )
        html = tmpl.render(title="Big", size="xl")
        assert "max-w-4xl" in html
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pytest tests/unit/test_phase2_fragments.py -v
```

Expected: All tests pass (the fragments were created in prior tasks).

- [ ] **Step 3: Lint and commit**

```bash
ruff check tests/unit/test_phase2_fragments.py --fix
ruff format tests/unit/test_phase2_fragments.py
git add tests/unit/test_phase2_fragments.py
git commit -m "test: add rendering tests for Phase 2 UI fragments"
```

---

### Task 9: Full Test Suite Verification + Version Bump

**Files:** None new (verification + bump)

- [ ] **Step 1: Run all Phase 2 tests together**

```bash
pytest tests/unit/test_breadcrumbs.py tests/unit/test_phase2_fragments.py -v
```

- [ ] **Step 2: Run full unit test suite**

```bash
pytest tests/ -m "not e2e" -x -q
```

- [ ] **Step 3: Run linting on all new files**

```bash
ruff check src/dazzle_back/runtime/breadcrumbs.py tests/unit/test_breadcrumbs.py tests/unit/test_phase2_fragments.py --fix
ruff format src/dazzle_back/runtime/breadcrumbs.py tests/unit/test_breadcrumbs.py tests/unit/test_phase2_fragments.py
```

- [ ] **Step 4: Run mypy on breadcrumbs module**

```bash
mypy src/dazzle_back/runtime/breadcrumbs.py
```

- [ ] **Step 5: Bump version and ship**

Run `/bump patch` then `/ship`.
