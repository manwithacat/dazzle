# Design Studio

A brand and design asset management app demonstrating Dazzle's UX component expansion (Phases 1-4).

## Components Exercised

| Component | Where Used |
|-----------|-----------|
| Color picker (Pickr) | Brand primary/secondary/accent colors |
| Rich text (Quill) | Asset descriptions, campaign briefs, feedback |
| Tags (Tom Select) | Asset categorization |
| Combobox (Tom Select) | Brand selection |
| Slider/range | Quality score, feedback rating |
| Date picker (Flatpickr) | Campaign schedule dates |
| Status cards | Asset overview by brand |
| Grid display | Brand cards, asset gallery |
| Queue display | Asset review queue |
| Metrics | Campaign dashboard |
| Steps indicator | Asset approval workflow (draft → review → approved → published) |

## Running

```bash
cd examples/design_studio
dazzle serve --local
```

- UI: http://localhost:3000
- API: http://localhost:8000/docs
