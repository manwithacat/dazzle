# UX Component Expansion — Phase 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the infrastructure for the UX component expansion — vendor new HTMX extensions and Alpine plugins, build the component lifecycle bridge, add response helpers for toasts/OOB swaps, and add conditional asset loading.

**Architecture:** Four new HTMX extensions and three Alpine plugins are vendored into `static/vendor/`. A `dz-component-bridge.js` generalizes the island mount/unmount pattern for vendored widgets. `response_helpers.py` provides server-side helpers for OOB swaps. `asset_manifest.py` derives required JS assets from surface specs. `base.html` gains container elements and conditional script loading.

**Tech Stack:** HTMX extensions (remove-me, class-tools, multi-swap, path-deps), Alpine.js plugins (@alpinejs/anchor, @alpinejs/collapse, @alpinejs/focus), Jinja2, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-28-ux-component-expansion-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_ui/runtime/static/vendor/htmx-ext-remove-me.js` | Create | HTMX remove-me extension |
| `src/dazzle_ui/runtime/static/vendor/htmx-ext-class-tools.js` | Create | HTMX class-tools extension |
| `src/dazzle_ui/runtime/static/vendor/htmx-ext-multi-swap.js` | Create | HTMX multi-swap extension |
| `src/dazzle_ui/runtime/static/vendor/htmx-ext-path-deps.js` | Create | HTMX path-deps extension |
| `src/dazzle_ui/runtime/static/vendor/alpine-anchor.min.js` | Create | Alpine anchor plugin |
| `src/dazzle_ui/runtime/static/vendor/alpine-collapse.min.js` | Create | Alpine collapse plugin |
| `src/dazzle_ui/runtime/static/vendor/alpine-focus.min.js` | Create | Alpine focus plugin |
| `src/dazzle_ui/runtime/static/js/dz-component-bridge.js` | Create | HTMX lifecycle bridge for vendored widgets |
| `src/dazzle_back/runtime/response_helpers.py` | Create | OOB swap helpers (with_toast, with_oob) |
| `src/dazzle_back/runtime/asset_manifest.py` | Create | Derives required JS assets from surface specs |
| `src/dazzle_ui/templates/base.html` | Modify | Add containers, extensions, conditional loading |
| `tests/unit/test_response_helpers.py` | Create | Tests for OOB swap helpers |
| `tests/unit/test_asset_manifest.py` | Create | Tests for asset derivation |
| `tests/unit/test_component_bridge.py` | Create | Tests for bridge script output |

---

### Task 1: Vendor HTMX Extensions

**Files:**
- Create: `src/dazzle_ui/runtime/static/vendor/htmx-ext-remove-me.js`
- Create: `src/dazzle_ui/runtime/static/vendor/htmx-ext-class-tools.js`
- Create: `src/dazzle_ui/runtime/static/vendor/htmx-ext-multi-swap.js`
- Create: `src/dazzle_ui/runtime/static/vendor/htmx-ext-path-deps.js`

- [ ] **Step 1: Download the four HTMX extensions**

Download from the official HTMX extensions repo. These are small, self-contained JS files.

```bash
cd /Volumes/SSD/Dazzle/src/dazzle_ui/runtime/static/vendor

# remove-me: auto-removes elements after a delay
curl -sL "https://unpkg.com/htmx-ext-remove-me@2.0.0/remove-me.js" -o htmx-ext-remove-me.js

# class-tools: add/remove/toggle CSS classes with timing
curl -sL "https://unpkg.com/htmx-ext-class-tools@2.0.0/class-tools.js" -o htmx-ext-class-tools.js

# multi-swap: swap multiple targets from a single response
curl -sL "https://unpkg.com/htmx-ext-multi-swap@2.0.0/multi-swap.js" -o htmx-ext-multi-swap.js

# path-deps: declare path dependencies for auto-refresh
curl -sL "https://unpkg.com/htmx-ext-path-deps@2.0.0/path-deps.js" -o htmx-ext-path-deps.js
```

Note: If any of the above URLs 404 or the version numbers differ, check https://extensions.htmx.org/ for the current package names and versions. The HTMX 2.x extensions use the `htmx-ext-*` naming convention. If Dazzle uses HTMX 1.x (check `htmx.min.js` header), use the 1.x-compatible versions from `https://unpkg.com/htmx.org@1.x/dist/ext/remove-me.js` instead.

- [ ] **Step 2: Verify each file downloaded correctly**

```bash
# Each file should be non-empty and contain the extension name
head -3 htmx-ext-remove-me.js
head -3 htmx-ext-class-tools.js
head -3 htmx-ext-multi-swap.js
head -3 htmx-ext-path-deps.js
```

Expected: Each file starts with a comment or IIFE containing the extension logic. If any file contains HTML (a 404 page), re-download with the correct URL.

- [ ] **Step 3: Commit vendored extensions**

```bash
git add src/dazzle_ui/runtime/static/vendor/htmx-ext-remove-me.js \
        src/dazzle_ui/runtime/static/vendor/htmx-ext-class-tools.js \
        src/dazzle_ui/runtime/static/vendor/htmx-ext-multi-swap.js \
        src/dazzle_ui/runtime/static/vendor/htmx-ext-path-deps.js
git commit -m "vendor: add HTMX extensions (remove-me, class-tools, multi-swap, path-deps)"
```

---

### Task 2: Vendor Alpine.js Plugins

**Files:**
- Create: `src/dazzle_ui/runtime/static/vendor/alpine-anchor.min.js`
- Create: `src/dazzle_ui/runtime/static/vendor/alpine-collapse.min.js`
- Create: `src/dazzle_ui/runtime/static/vendor/alpine-focus.min.js`

- [ ] **Step 1: Download the three Alpine plugins**

```bash
cd /Volumes/SSD/Dazzle/src/dazzle_ui/runtime/static/vendor

# @alpinejs/anchor — Floating UI positioning for popovers/tooltips
curl -sL "https://cdn.jsdelivr.net/npm/@alpinejs/anchor@3.x.x/dist/cdn.min.js" -o alpine-anchor.min.js

# @alpinejs/collapse — smooth height transition for accordion
curl -sL "https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.x.x/dist/cdn.min.js" -o alpine-collapse.min.js

# @alpinejs/focus — focus trapping for modals/slide-overs
curl -sL "https://cdn.jsdelivr.net/npm/@alpinejs/focus@3.x.x/dist/cdn.min.js" -o alpine-focus.min.js
```

Note: The `3.x.x` in jsDelivr resolves to the latest 3.x release. Pin to exact versions if you want reproducible builds — check the downloaded file headers for the resolved version. The existing Alpine plugins (`alpine-sort.min.js`, `alpine-persist.min.js`) follow the `alpine-{name}.min.js` naming convention.

- [ ] **Step 2: Verify each file downloaded correctly**

```bash
# Should be non-empty JS, not HTML 404 pages
wc -c alpine-anchor.min.js alpine-collapse.min.js alpine-focus.min.js
```

Expected: anchor ~4KB, collapse ~2KB, focus ~3KB. If any file is suspiciously small (<100 bytes) or large (>50KB), the download may have failed.

- [ ] **Step 3: Commit vendored plugins**

```bash
git add src/dazzle_ui/runtime/static/vendor/alpine-anchor.min.js \
        src/dazzle_ui/runtime/static/vendor/alpine-collapse.min.js \
        src/dazzle_ui/runtime/static/vendor/alpine-focus.min.js
git commit -m "vendor: add Alpine.js plugins (anchor, collapse, focus)"
```

---

### Task 3: Wire New Extensions and Plugins into base.html

**Files:**
- Modify: `src/dazzle_ui/templates/base.html`

- [ ] **Step 1: Add HTMX extensions to the script block**

In `base.html`, after line 39 (`htmx-ext-sse.js`), add the four new extensions:

```html
  <script src="{{ 'vendor/htmx-ext-remove-me.js' | static_url }}"></script>
  <script src="{{ 'vendor/htmx-ext-class-tools.js' | static_url }}"></script>
  <script src="{{ 'vendor/htmx-ext-multi-swap.js' | static_url }}"></script>
  <script src="{{ 'vendor/htmx-ext-path-deps.js' | static_url }}"></script>
```

- [ ] **Step 2: Add Alpine plugins to the plugin block**

After line 43 (`alpine-persist.min.js`), before `dz-alpine.js`, add:

```html
  <script defer src="{{ 'vendor/alpine-anchor.min.js' | static_url }}"></script>
  <script defer src="{{ 'vendor/alpine-collapse.min.js' | static_url }}"></script>
  <script defer src="{{ 'vendor/alpine-focus.min.js' | static_url }}"></script>
```

Critical: these must load BEFORE `dz-alpine.js` (line 44) and BEFORE `alpine.min.js` (line 46) to ensure they register before Alpine starts.

- [ ] **Step 3: Update hx-ext on body tag**

Change line 97 from:

```html
<body class="min-h-screen bg-base-200" style="font-family: var(--font-sans)" hx-boost="true" hx-ext="morph,preload,response-targets,loading-states">
```

To:

```html
<body class="min-h-screen bg-base-200" style="font-family: var(--font-sans)" hx-boost="true" hx-ext="morph,preload,response-targets,loading-states,remove-me,class-tools,multi-swap,path-deps">
```

- [ ] **Step 4: Add container elements for toasts, modal slot, and dynamic assets**

After the existing toast div (line 110, after `</div>` closing the `dz-toast` div), add:

```html
  {# Toast container for HTMX OOB-driven toasts (remove-me auto-dismiss) #}
  <div id="dz-toast-container" class="toast toast-end toast-top" aria-live="polite"></div>

  {# Modal slot for server-loaded modals #}
  <div id="dz-modal-slot"></div>

  {# Dynamic asset loader for HTMX-swapped widget dependencies #}
  <div id="dz-dynamic-assets"></div>
```

Note: `dz-toast-container` is separate from the existing Alpine `dz-toast` div. The existing Alpine toast system remains for backward compatibility. The new container is for HTMX OOB-driven toasts using `remove-me`.

- [ ] **Step 5: Add conditional asset loading block**

Before the closing `{% block scripts_extra %}` (line 130), add:

```html
  {# Conditional vendor widget assets — populated by asset_manifest #}
  {% if required_assets is defined %}
  {% if "tom-select" in required_assets %}
  <link rel="stylesheet" href="{{ 'vendor/tom-select.css' | static_url }}">
  <script defer src="{{ 'vendor/tom-select.min.js' | static_url }}"></script>
  {% endif %}
  {% if "flatpickr" in required_assets %}
  <link rel="stylesheet" href="{{ 'vendor/flatpickr.css' | static_url }}">
  <script defer src="{{ 'vendor/flatpickr.min.js' | static_url }}"></script>
  {% endif %}
  {% if "pickr" in required_assets %}
  <link rel="stylesheet" href="{{ 'vendor/pickr.css' | static_url }}">
  <script defer src="{{ 'vendor/pickr.min.js' | static_url }}"></script>
  {% endif %}
  {% if "quill" in required_assets %}
  <link rel="stylesheet" href="{{ 'vendor/quill.snow.css' | static_url }}">
  <script defer src="{{ 'vendor/quill.min.js' | static_url }}"></script>
  {% endif %}
  {% endif %}
```

Note: The actual vendor files for Tom Select, Flatpickr, Pickr, and Quill will be added in Phase 4. This block is the loading mechanism — it's safe to add now because the `{% if %}` guards prevent loading non-existent files unless `required_assets` is explicitly set.

- [ ] **Step 6: Verify base.html renders without errors**

```bash
cd /Volumes/SSD/Dazzle
python -c "
from dazzle_ui.runtime.template_renderer import create_jinja_env
env = create_jinja_env()
tmpl = env.get_template('base.html')
html = tmpl.render(
    _htmx_partial=False,
    _use_cdn=False,
    _tailwind_bundled=False,
    _dazzle_version='0.51.0',
    app_name='Test',
)
assert 'remove-me' in html
assert 'dz-toast-container' in html
assert 'dz-modal-slot' in html
assert 'dz-dynamic-assets' in html
assert 'alpine-anchor' in html
print('OK: base.html renders with all new elements')
"
```

Expected: `OK: base.html renders with all new elements`

- [ ] **Step 7: Commit base.html changes**

```bash
git add src/dazzle_ui/templates/base.html
git commit -m "feat(ui): wire HTMX extensions + Alpine plugins + container elements into base.html"
```

---

### Task 4: Build the Component Lifecycle Bridge

**Files:**
- Create: `src/dazzle_ui/runtime/static/js/dz-component-bridge.js`
- Create: `tests/unit/test_component_bridge.py`

- [ ] **Step 1: Write the test for bridge script existence and structure**

```python
# tests/unit/test_component_bridge.py
"""Tests for the dz-component-bridge.js script."""

import pathlib

import pytest

BRIDGE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-component-bridge.js"
)


def test_bridge_script_exists():
    assert BRIDGE_PATH.exists(), f"Bridge script not found at {BRIDGE_PATH}"


def test_bridge_script_has_required_patterns():
    content = BRIDGE_PATH.read_text()
    # Must listen for HTMX lifecycle events
    assert "htmx:beforeSwap" in content
    assert "htmx:afterSettle" in content
    # Must scan for data-dz-widget elements
    assert "data-dz-widget" in content
    # Must expose a registration function
    assert "registerWidget" in content


def test_bridge_script_is_iife():
    """Bridge must be wrapped in an IIFE to avoid polluting global scope."""
    content = BRIDGE_PATH.read_text().strip()
    assert content.startswith("(function")
    assert content.endswith("})();") or content.endswith("})();\n")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_component_bridge.py -v
```

Expected: FAIL — `test_bridge_script_exists` fails because the file doesn't exist yet.

- [ ] **Step 3: Write the component bridge script**

```javascript
// src/dazzle_ui/runtime/static/js/dz-component-bridge.js
/**
 * Dazzle Component Bridge — manages vendored widget lifecycle across HTMX swaps.
 *
 * Each widget mount point is an element with:
 *   data-dz-widget   — widget type key (e.g., "datepicker", "combobox")
 *   data-dz-options  — JSON-encoded options for the widget
 *
 * Widget types are registered via window.dz.bridge.registerWidget(type, { mount, unmount }).
 *   mount(el, options)   — initialize the widget on the element, return instance
 *   unmount(el, instance) — tear down the widget
 *
 * The bridge hooks into HTMX lifecycle events:
 *   htmx:beforeSwap  — unmount widgets in the swap target
 *   htmx:afterSettle — mount widgets in the swapped content
 */
(function () {
  var REGISTRY = {};
  var INSTANCES = new WeakMap();

  function mountWidgets(root) {
    var els = root.querySelectorAll("[data-dz-widget]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (INSTANCES.has(el)) continue;
      var type = el.dataset.dzWidget;
      var handler = REGISTRY[type];
      if (!handler) continue;
      var options = {};
      try { options = JSON.parse(el.dataset.dzOptions || "{}"); } catch (_) {}
      try {
        var instance = handler.mount(el, options);
        INSTANCES.set(el, { type: type, instance: instance });
      } catch (e) {
        console.error("[dz-bridge] Failed to mount widget \"" + type + "\":", e);
      }
    }
  }

  function unmountWidgets(root) {
    if (!root || root.nodeType !== 1) return;
    var els = root.querySelectorAll
      ? root.querySelectorAll("[data-dz-widget]")
      : [];
    // Also check root itself
    var targets = root.matches && root.matches("[data-dz-widget]")
      ? [root].concat(Array.prototype.slice.call(els))
      : Array.prototype.slice.call(els);
    for (var i = 0; i < targets.length; i++) {
      var el = targets[i];
      var entry = INSTANCES.get(el);
      if (!entry) continue;
      var handler = REGISTRY[entry.type];
      if (handler && typeof handler.unmount === "function") {
        try { handler.unmount(el, entry.instance); } catch (_) {}
      }
      INSTANCES.delete(el);
    }
  }

  function registerWidget(type, handler) {
    if (!type || !handler || typeof handler.mount !== "function") {
      console.error("[dz-bridge] registerWidget requires type and { mount } handler");
      return;
    }
    REGISTRY[type] = handler;
  }

  // Expose on window.dz namespace
  window.dz = window.dz || {};
  window.dz.bridge = {
    registerWidget: registerWidget,
    mountWidgets: mountWidgets,
    unmountWidgets: unmountWidgets,
  };

  document.addEventListener("DOMContentLoaded", function () {
    mountWidgets(document);
    document.body.addEventListener("htmx:afterSettle", function (e) {
      mountWidgets(e.target);
    });
    document.body.addEventListener("htmx:beforeSwap", function (e) {
      if (e.detail && e.detail.target) {
        unmountWidgets(e.detail.target);
      }
    });
  });
})();
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_component_bridge.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Wire bridge into base.html**

In `base.html`, add the bridge script after `dz-islands.js` (currently line 50):

```html
  <script defer src="{{ 'js/dz-component-bridge.js' | static_url }}"></script>
```

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_ui/runtime/static/js/dz-component-bridge.js \
        tests/unit/test_component_bridge.py \
        src/dazzle_ui/templates/base.html
git commit -m "feat(ui): add component lifecycle bridge for vendored widgets"
```

---

### Task 5: Build Response Helpers

**Files:**
- Create: `src/dazzle_back/runtime/response_helpers.py`
- Create: `tests/unit/test_response_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_response_helpers.py
"""Tests for HTMX OOB response helpers."""

import pytest
from starlette.responses import HTMLResponse

from dazzle_back.runtime.response_helpers import with_oob, with_toast


class TestWithToast:
    def test_appends_toast_html_to_response(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Saved successfully", "success")
        body = result.body.decode()
        assert "<p>OK</p>" in body
        assert 'id="dz-toast-container"' in body
        assert "hx-swap-oob" in body
        assert "Saved successfully" in body
        assert "alert-success" in body

    def test_default_level_is_info(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Hello")
        body = result.body.decode()
        assert "alert-info" in body

    def test_includes_remove_me_attribute(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Gone soon", "warning")
        body = result.body.decode()
        assert 'remove-me="5s"' in body

    def test_escapes_html_in_message(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "<script>alert('xss')</script>", "error")
        body = result.body.decode()
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_preserves_response_status_code(self):
        resp = HTMLResponse("<p>Created</p>", status_code=201)
        result = with_toast(resp, "Created", "success")
        assert result.status_code == 201

    def test_preserves_existing_headers(self):
        resp = HTMLResponse("<p>OK</p>")
        resp.headers["X-Custom"] = "test"
        result = with_toast(resp, "Done")
        assert result.headers.get("X-Custom") == "test"


class TestWithOob:
    def test_appends_oob_swap_to_response(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "sidebar", "<ul><li>New item</li></ul>")
        body = result.body.decode()
        assert "<p>Main</p>" in body
        assert 'id="sidebar"' in body
        assert 'hx-swap-oob="innerHTML"' in body
        assert "<ul><li>New item</li></ul>" in body

    def test_custom_swap_strategy(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "nav", "<nav>Updated</nav>", swap="outerHTML")
        body = result.body.decode()
        assert 'hx-swap-oob="outerHTML"' in body

    def test_multiple_oob_swaps(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "a", "<div>A</div>")
        result = with_oob(result, "b", "<div>B</div>")
        body = result.body.decode()
        assert 'id="a"' in body
        assert 'id="b"' in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_response_helpers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle_back.runtime.response_helpers'`

- [ ] **Step 3: Implement response helpers**

```python
# src/dazzle_back/runtime/response_helpers.py
"""
HTMX OOB swap response helpers.

Provides utilities for appending out-of-band HTML fragments to any
HTMLResponse, enabling server-driven toasts, breadcrumbs, and other
UI updates without client-side logic.
"""

from __future__ import annotations

from html import escape

from starlette.responses import HTMLResponse


def with_toast(
    response: HTMLResponse,
    message: str,
    level: str = "info",
    duration: str = "5s",
) -> HTMLResponse:
    """Append an auto-dismissing toast to an HTMX response via OOB swap.

    The toast is injected into ``#dz-toast-container`` using the
    ``remove-me`` HTMX extension for auto-dismissal.

    Args:
        response: The original HTMLResponse to augment.
        message: Toast message text (HTML-escaped automatically).
        level: DaisyUI alert level — ``success``, ``error``, ``warning``, ``info``.
        duration: Auto-dismiss delay (e.g., ``"5s"``).
    """
    safe_message = escape(message)
    toast_html = (
        f'<div id="dz-toast-container" hx-swap-oob="afterbegin:#dz-toast-container">'
        f'<div class="alert alert-{level}" remove-me="{duration}">'
        f"<span>{safe_message}</span>"
        f"</div>"
        f"</div>"
    )
    return _append_html(response, toast_html)


def with_oob(
    response: HTMLResponse,
    target_id: str,
    html: str,
    swap: str = "innerHTML",
) -> HTMLResponse:
    """Append an OOB swap fragment to an HTMX response.

    Args:
        response: The original HTMLResponse to augment.
        target_id: The ``id`` of the target element.
        html: The HTML content to swap in.
        swap: The swap strategy (``innerHTML``, ``outerHTML``, ``afterbegin``, etc.).
    """
    oob_html = f'<div id="{target_id}" hx-swap-oob="{swap}">{html}</div>'
    return _append_html(response, oob_html)


def _append_html(response: HTMLResponse, fragment: str) -> HTMLResponse:
    """Append HTML fragment to an existing HTMLResponse, preserving headers and status."""
    existing_body = response.body.decode("utf-8")
    new_body = existing_body + fragment
    new_response = HTMLResponse(
        content=new_body,
        status_code=response.status_code,
        media_type=response.media_type,
    )
    for key, value in response.headers.items():
        if key.lower() != "content-length":
            new_response.headers[key] = value
    return new_response
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_response_helpers.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/response_helpers.py \
        tests/unit/test_response_helpers.py
git commit -m "feat(runtime): add HTMX OOB response helpers (with_toast, with_oob)"
```

---

### Task 6: Build Asset Manifest

**Files:**
- Create: `src/dazzle_back/runtime/asset_manifest.py`
- Create: `tests/unit/test_asset_manifest.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_asset_manifest.py
"""Tests for conditional JS asset derivation from surface specs."""

import pytest

from dazzle_back.runtime.asset_manifest import collect_required_assets


class _FakeField:
    """Minimal field stub for testing."""

    def __init__(self, field_type: str = "str", widget: str | None = None):
        self.type = field_type
        self.widget = widget


class _FakeSurface:
    """Minimal surface stub for testing."""

    def __init__(self, fields: list[_FakeField]):
        self.fields = fields


class TestCollectRequiredAssets:
    def test_no_widgets_returns_empty(self):
        surface = _FakeSurface([_FakeField("str"), _FakeField("int")])
        assert collect_required_assets(surface) == set()

    def test_rich_text_requires_quill(self):
        surface = _FakeSurface([_FakeField("text", widget="rich_text")])
        assert collect_required_assets(surface) == {"quill"}

    def test_combobox_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("ref", widget="combobox")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_multi_select_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("ref", widget="multi_select")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_tags_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("str", widget="tags")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_date_picker_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("date", widget="picker")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_datetime_picker_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("datetime", widget="picker")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_date_range_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("date", widget="range")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_color_requires_pickr(self):
        surface = _FakeSurface([_FakeField("str", widget="color")])
        assert collect_required_assets(surface) == {"pickr"}

    def test_multiple_widgets_collect_all(self):
        surface = _FakeSurface([
            _FakeField("text", widget="rich_text"),
            _FakeField("ref", widget="combobox"),
            _FakeField("date", widget="picker"),
            _FakeField("str", widget="color"),
        ])
        assert collect_required_assets(surface) == {
            "quill", "tom-select", "flatpickr", "pickr",
        }

    def test_duplicate_widgets_deduplicated(self):
        surface = _FakeSurface([
            _FakeField("ref", widget="combobox"),
            _FakeField("ref", widget="multi_select"),
            _FakeField("str", widget="tags"),
        ])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_unknown_widget_ignored(self):
        surface = _FakeSurface([_FakeField("str", widget="unknown_future_widget")])
        assert collect_required_assets(surface) == set()

    def test_non_date_type_with_picker_widget_ignored(self):
        """Picker widget only applies to date/datetime fields."""
        surface = _FakeSurface([_FakeField("str", widget="picker")])
        assert collect_required_assets(surface) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_asset_manifest.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle_back.runtime.asset_manifest'`

- [ ] **Step 3: Implement asset manifest**

```python
# src/dazzle_back/runtime/asset_manifest.py
"""
Conditional JS asset derivation from surface field specs.

Walks the fields of a surface and collects which vendor widget libraries
are needed, so base.html can conditionally load only the required scripts.
"""

from __future__ import annotations

from typing import Any, Protocol


class _HasWidget(Protocol):
    type: str
    widget: str | None


class _HasFields(Protocol):
    fields: list[Any]


# Maps (widget, optional type constraint) → vendor asset key
_WIDGET_ASSET_MAP: dict[str, str | tuple[str, set[str]]] = {
    "rich_text": "quill",
    "combobox": "tom-select",
    "multi_select": "tom-select",
    "tags": "tom-select",
    "color": "pickr",
    # picker and range only apply to date/datetime fields
    "picker": ("flatpickr", {"date", "datetime"}),
    "range": ("flatpickr", {"date", "datetime"}),
}


def collect_required_assets(surface: _HasFields) -> set[str]:
    """Derive the set of vendor JS asset keys required by a surface's fields.

    Returns a set of strings like ``{"quill", "tom-select", "flatpickr"}``.
    These keys correspond to conditional blocks in ``base.html``.
    """
    assets: set[str] = set()
    for field in surface.fields:
        widget = getattr(field, "widget", None)
        if not widget:
            continue
        mapping = _WIDGET_ASSET_MAP.get(widget)
        if mapping is None:
            continue
        if isinstance(mapping, tuple):
            asset_key, allowed_types = mapping
            field_type = getattr(field, "type", "")
            if field_type in allowed_types:
                assets.add(asset_key)
        else:
            assets.add(mapping)
    return assets
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_asset_manifest.py -v
```

Expected: All 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/asset_manifest.py \
        tests/unit/test_asset_manifest.py
git commit -m "feat(runtime): add asset manifest — derives vendor JS deps from surface specs"
```

---

### Task 7: Run Full Test Suite and Verify No Regressions

**Files:** None (verification only)

- [ ] **Step 1: Run existing unit tests**

```bash
pytest tests/ -m "not e2e" -x -q
```

Expected: All ~3399+ existing tests pass. The new files don't modify any existing behavior — they only add new modules and static assets.

- [ ] **Step 2: Run linting**

```bash
ruff check src/dazzle_back/runtime/response_helpers.py src/dazzle_back/runtime/asset_manifest.py tests/unit/test_response_helpers.py tests/unit/test_asset_manifest.py tests/unit/test_component_bridge.py --fix
ruff format src/dazzle_back/runtime/response_helpers.py src/dazzle_back/runtime/asset_manifest.py tests/unit/test_response_helpers.py tests/unit/test_asset_manifest.py tests/unit/test_component_bridge.py
```

Expected: No errors, or auto-fixed formatting.

- [ ] **Step 3: Run mypy on new modules**

```bash
mypy src/dazzle_back/runtime/response_helpers.py src/dazzle_back/runtime/asset_manifest.py
```

Expected: No type errors.

- [ ] **Step 4: Commit any lint/format fixes**

```bash
git add -u
git diff --cached --stat
# Only commit if there are changes
git diff --cached --quiet || git commit -m "style: lint and format Phase 1 modules"
```

- [ ] **Step 5: Verify base.html renders in a real app context**

```bash
cd /Volumes/SSD/Dazzle
dazzle validate examples/simple_task/
```

Expected: Validation passes. This confirms the DSL + template pipeline still works end-to-end.

---

### Task 8: Version Bump and Final Commit

**Files:** None (uses /bump command)

- [ ] **Step 1: Bump patch version**

Run `/bump patch` to increment the version.

- [ ] **Step 2: Verify clean worktree**

```bash
git status
```

Expected: Clean worktree. All changes committed.

- [ ] **Step 3: Push**

```bash
git push
```
