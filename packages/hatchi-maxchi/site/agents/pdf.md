# PDF viewer (`pdf`)

The hx-pdf viewing shell: server-authorized bytes, lazy PDF.js rendering, toolbar slots for paging/zoom, URL deep-links — progressive enhancement over a download link.

## Partial (copy-paste; the live demo renders this exact string)

```html
<section class="pdf" data-pdf data-pdf-src="sample.pdf" data-pdf-lib="https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.min.mjs" data-pdf-worker="https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.worker.min.mjs">
  <header class="pdf-toolbar" data-pdf-toolbar>
    <button type="button" class="button" data-size="sm" data-variant="outline" data-pdf-prev>Previous</button>
    <label>Page <input class="pdf-page-input" data-pdf-page value="1" inputmode="numeric" aria-label="Page number"></label>
    <span class="pdf-page-count" data-pdf-page-count></span>
    <button type="button" class="button" data-size="sm" data-variant="outline" data-pdf-next>Next</button>
    <span class="pdf-toolbar-spacer"></span>
    <button type="button" class="button" data-size="sm" data-variant="outline" data-pdf-zoom-out aria-label="Zoom out">−</button>
    <button type="button" class="button" data-size="sm" data-variant="outline" data-pdf-zoom-in aria-label="Zoom in">+</button>
    <button type="button" class="button" data-size="sm" data-variant="outline" data-pdf-fit-width>Fit width</button>
    <a href="sample.pdf" class="button" data-size="sm" data-variant="ghost" data-pdf-download-link download>Download</a>
  </header>
  <div class="pdf-status" data-pdf-status aria-live="polite"></div>
  <div class="pdf-stage" data-pdf-viewer tabindex="0">
    <noscript><a href="sample.pdf" download>Download PDF</a></noscript>
  </div>
</section>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /_dazzle/documents/{entity}/{id}/{field}/file` | PDF.js fetching document bytes (initial + Range requests as the user pages) | the file field's bytes — 200 whole-body or 206 partial with Content-Range; opaque 404 when the record is out of scope; 416 for unsatisfiable ranges | none (bytes consumed by the rendering engine) | — |

## Contract modules (typed source of truth)

Epistemic lock: do not invent attrs or response shapes that diverge from these modules. CI validates exemplars against `DOM_CONTRACT` (`tests/test_contracts.py`).

### `contracts/pdf.py`

- **DOM root:** `[data-dz-pdf]` (part `pdf`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-pdf]` | `data-dz-pdf-src` | present (any value) |
| `[data-dz-pdf]` | `data-dz-pdf-lib` | present (any value) |
| `[data-dz-pdf-viewer]` | `—` | — |

**Module source**

```python
"""HYPERPART: pdf — progressive PDF shell (access + lazy PDF.js)."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pdf",
    root="[data-dz-pdf]",
    nodes=(
        Node(
            "[data-dz-pdf]",
            attrs={
                "data-dz-pdf-src": Present(),
                "data-dz-pdf-lib": Present(),
            },
        ),
        Node("[data-dz-pdf-viewer]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Guidance (structured)

### Seams

- data-dz-pdf-src points at the document bytes (or range proxy)
- data-dz-pdf-lib lazy-loads PDF.js as an ES module on first intersect
- data-dz-pdf-state=url enables ?dzpdf-page / ?dzpdf-zoom deep-links

### Pitfalls

- application controls ACCESS; PDF.js only renders — do not embed bytes in the bundle
- without JS the noscript download link IS the experience

### Keyboard / AT

- toolbar page/zoom controls remain keyboard-operable
- noscript download is the progressive-enhancement floor

### Do / Don't

| Do | Don't |
|---|---|
| lazy-load the engine from data-dz-pdf-lib when the viewer enters view | eager-import PDF.js on every page that might show a document |

### Composes with

- `button` (agents/button.md)

## Guidance (prose; HTML from the registry notes field)

The application renders the shell and CONTROLS ACCESS; PDF.js renders the document. <code>dz-pdf.js</code> lazy-loads the library as an ES module from <code>data-dz-pdf-lib</code> only when the viewer scrolls into view — no PDF bytes or engine in the bundle. In Dazzle, <code>data-dz-pdf-src</code> points at the scope-gated range proxy (<code>/_dazzle/documents/{entity}/{id}/{field}/file</code> — document access IS entity access), and PDF.js range-requests pages on demand. <code>data-dz-pdf-state=&quot;url&quot;</code> opts a viewer into <code>?dzpdf-page/?dzpdf-zoom</code> deep-links (replaceState — Back stays page navigation). Without JS the noscript download link is the whole experience. In production, VENDOR the PDF.js module — dynamic import() cannot carry SRI; the gallery's CDN pin is demo-only.

## Controller files

- `controllers/dz-pdf.js`
