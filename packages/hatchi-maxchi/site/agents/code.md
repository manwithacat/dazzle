# Code block (`code`)

Fenced code surface with optional language chip and copy control — server-emitted chrome for docs and samples. Syntax colour is build-time token spans (Python), not a browser highlighter.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<figure class="code" data-code data-language="python">
  <div class="code__meta"><span class="code__lang">python</span><button type="button" class="code__copy" data-code-copy aria-label="Copy code to clipboard"><span class="code__copy-idle">Copy</span><span class="code__copy-done">Copied</span></button></div>
  <pre class="code__pre" tabindex="0" role="region" aria-label="Python example"><code class="code__source">def greet(name: str) -> str:
    """Return a friendly hello."""
    return f"Hello, {name}"
</code></pre>
</figure>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- figure[data-dz-code] → div.dz-code__meta → pre.dz-code__pre > code.dz-code__source
- meta flex row: optional .dz-code__lang, optional [data-dz-code-copy] (CSS margin-inline-start:auto keeps copy trailing)
- build-time token spans (.dz-code__tok--*) for Python and HTML colour
- surface uses light-dark() — follows [data-theme], not always-dark

### Do / Don't

| Do | Don't |
|---|---|
| emit figure > .dz-code__meta > (lang? + copy?) > pre > code | absolute-position the copy control or invent a one-off toolbar |

### Pitfalls

- do not absolute-position .dz-code__copy — it drifts left inside nested min-width:0 containers (Hyperpart detail pages); use the meta flex row
- do not put copy/lang as direct children of the figure without .dz-code__meta
- do not ship a browser syntax engine for static docs — highlight at build (python + html/svg/xml only today)
- copy must read textContent (not innerHTML) so spans never paste

### Keyboard / AT

- pre is a keyboard-scrollable region (tabindex=0)
- copy button is a real button with aria-label

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/code.py`

- **Required root:** `[data-dz-code]` (part `code`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-code]` | `data-dz-code` | present (any value) |
| `[data-dz-code-copy]` | `data-dz-code-copy` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: code — fenced code surface (root + optional copy control)."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="code",
    root="[data-dz-code]",
    nodes=(
        Node("[data-dz-code]", attrs={"data-dz-code": Present()}),
        # Copy is optional chrome; when present the attr marks the control.
        Node("[data-dz-code-copy]", attrs={"data-dz-code-copy": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Use the code Hyperpart for any fenced sample in docs or app chrome. Required nesting: figure.dz-code[data-dz-code] → div.dz-code__meta (optional lang + optional copy) → pre.dz-code__pre → code.dz-code__source. Copy is pushed trailing by CSS (margin-inline-start: auto on the button) — do not absolute-position it (nested part-page flex/min-width:0 chains left-shift absolute children). The gallery builder runs a stdlib highlighter (site/highlight.py) for Python and HTML into dz-code__tok--* spans; copy uses textContent so spans never paste. Omit the lang span when there is no language; omit the copy button when display-only (keep the meta bar if a lang chip remains). Scheme: the surface follows the page theme via light-dark() (light code on light pages, dark on dark) — not always-dark, so dense docs stay scannable.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/code.py`
- `controllers/dz-code.js`
