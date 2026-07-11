# Code block (`code`)

Fenced code surface with optional language chip and copy control — server-emitted chrome for docs and samples. Syntax colour is build-time token spans (Python), not a browser highlighter.

## Partial (copy-paste; the live demo renders this exact string)

```html
<figure class="code" data-code data-language="python">
  <div class="code__meta"><span class="code__lang">python</span><button type="button" class="code__copy" data-code-copy aria-label="Copy code to clipboard"><span class="code__copy-idle">Copy</span><span class="code__copy-done">Copied</span></button></div>
  <pre class="code__pre" tabindex="0" role="region" aria-label="Python example"><code class="code__source">def greet(name: str) -> str:
    """Return a friendly hello."""
    return f"Hello, {name}"
</code></pre>
</figure>
```

## Contract modules (typed source of truth)

Epistemic lock: do not invent attrs or response shapes that diverge from these modules. CI validates exemplars against `DOM_CONTRACT` (`tests/test_contracts.py`).

### `contracts/code.py`

- **DOM root:** `[data-dz-code]` (part `code`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-code]` | `data-dz-code` | present (any value) |
| `[data-dz-code-copy]` | `data-dz-code-copy` | present (any value) |

**Module source**

```python
"""HYPERPART: code — fenced code surface (root + optional copy control)."""

from __future__ import annotations

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

## Guidance (structured)

### Seams

- data-dz-code root marks the fenced surface
- data-dz-language optional chip; data-dz-code-copy optional control
- build-time token spans (.dz-code__tok--*) for Python colour

### Pitfalls

- do not ship a browser syntax engine for static docs — highlight at build
- copy must read textContent (not innerHTML) so spans never paste

### Keyboard / AT

- pre is a keyboard-scrollable region (tabindex=0)
- copy button is a real button with aria-label

### Do / Don't

| Do | Don't |
|---|---|
| emit figure.dz-code from the server/docs builder | paste Prism/Shiki client bundles just for gallery colour |

## Guidance (prose; HTML from the registry notes field)

Use the code Hyperpart for any fenced sample in docs or app chrome. The gallery builder runs a stdlib Python highlighter (<code>site/highlight.py</code>) that wraps tokens in <code>dz-code__tok--*</code> spans; copy always uses <code>textContent</code> so spans never reach the clipboard. Omit <code>data-dz-language</code> to hide the language chip; omit the copy button when the block is display-only.

## Controller files

- `controllers/dz-code.js`
