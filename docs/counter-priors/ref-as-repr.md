---
id: ref_as_repr
name: Ref as Python dict/UUID repr in buyer chrome
layer: inference
status: active
summary: >-
  Preferring raw FK entity dicts (or str(dict)) on queue/card meta so stills
  show Device: {'id': UUID(...)} instead of story codes / display names.
  Residual_total can stay 0 while Trust walk-out chrome is live (#1626 T1/T2).
triggers_text:
  - "UUID("
  - "dict repr"
  - "device meta"
  - "queue meta"
  - "Assigned To"
  - "ref_as_repr"
  - "person_as_text"
  - "presentation residual"
  - "hyperpart presentation"
  - "FT-PROBE"
triggers_code:
  - "UUID\\s*\\("
  - "\\{\\s*['\"]id['\"]"
  - "ref_as_repr"
  - "person_as_text"
  - "_format_queue_meta_value"
  - "str\\(raw\\)"
  - "product_quality"
  - "score_presentation"
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  kb_patterns: ["hyperpart_presentation", "empty_desk_false_green"]
  tests:
    - "tests/unit/test_queue_meta_density_1626.py"
    - "tests/unit/test_presentation_residual_1626.py"
    - "tests/unit/test_presentation_mcp_1626.py"
detectors: []
---

# Ref as Python dict/UUID repr in buyer chrome

## The corpus prior

Agents optimise **emit coverage** and **byte floors**. After person×queue_meta
Avatar work, preferring FK **entity dicts** for Avatar initials is correct for
people — but the same path stringifies **device/entity** dicts via `str(dict)`,
so buyers see `Device: {'id': UUID('…')}`. Floors and seed residual stay green
because they do not OCR still text. The prior is *“residual_total=0 means chrome
is honest.”*

## Wrong shape

```text
# Prefer any FK dict for queue meta
raw = item["device_id"]  # {"id": UUID(...)}  id-only join
value = str(raw)         # "{'id': UUID('…')}"
# product_quality residual_total = 0  (bytes + seeds only)
```

while `issue_triage_*` still shows Python repr and Trust collapses.

## Right shape

1. Prefer entity dict **only when it has display substance** (name/code/email/…);
   else `*_display` / `_ref_display_name` — never `str(dict)`.
2. Route person through `present(person, queue_meta)` → Avatar; non-person refs
   through human display names.
3. OBSERVE with:
   - MCP `product_quality(operation=score)` — residual_total includes presentation
   - MCP `presentation(operation=residual|opportunities|cognition)`
   - CLI `dazzle demo quality` / `dazzle qa hyperpart-opportunities`
4. Force `/improve framework-ux hyperpart_presentation` when presentation residual > 0.
5. Recapture hero stills after emit fix; open the PNG (stills beat claims).

## Why this matters here

Dazzle’s agent thesis is that tools form **true beliefs** about product surfaces.
A green residual coexisting with dict/UUID chrome is a **false belief** — the same
class as empty-desk false green, but for presentation honesty rather than seed
hits. #1626 antagonist 01 Aug b: fieldtest −1.0 despite residual_total=0.
