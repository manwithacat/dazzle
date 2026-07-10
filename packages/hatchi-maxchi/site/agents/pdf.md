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

## Guidance (prose; HTML from the registry notes field)

The application renders the shell and CONTROLS ACCESS; PDF.js renders the document. <code>dz-pdf.js</code> lazy-loads the library as an ES module from <code>data-dz-pdf-lib</code> only when the viewer scrolls into view — no PDF bytes or engine in the bundle. In Dazzle, <code>data-dz-pdf-src</code> points at the scope-gated range proxy (<code>/_dazzle/documents/{entity}/{id}/{field}/file</code> — document access IS entity access), and PDF.js range-requests pages on demand. <code>data-dz-pdf-state=&quot;url&quot;</code> opts a viewer into <code>?dzpdf-page/?dzpdf-zoom</code> deep-links (replaceState — Back stays page navigation). Without JS the noscript download link is the whole experience. In production, VENDOR the PDF.js module — dynamic import() cannot carry SRI; the gallery's CDN pin is demo-only.

## Controller files

- `controllers/dz-pdf.js`
