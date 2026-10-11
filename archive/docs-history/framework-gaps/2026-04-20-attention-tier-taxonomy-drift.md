# Attention-Tier Taxonomy Drift Across Workspace Regions

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-04-20** during Dazzle's autonomous-improvement cycles. It records the
    framework as it was then and the gap being worked at the time; **it may not
    describe current behaviour.** Start from the [documentation home](../../index.md),
    or see [Project Evolution](../../architecture/evolution.md) for how these fit together.


**Date**: 2026-04-20 (cycle 281)
**Class**: Framework-level consistency gap
**Status**: Open for implementation

## Problem statement

Four workspace regions surface per-row attention signals (`_attention` envelope on each item) but each renders the signal with a different taxonomy + visual encoding:

| Region | Tiers supported | Visual encoding |
|--------|-----------------|-----------------|
| `grid-region` (UX-066) | critical / warning / notice | 4px left border |
| `timeline-region` (UX-067) | critical / warning / *fallback to default* | SVG bullet marker colour (no `notice` tier) |
| `queue-region` (UX-068) | critical / warning / notice | 4px left border **AND** 0.04 alpha background tint |
| `list-region` (UX-069) | critical / warning / notice | 0.08 alpha background tint (critical/warning), 0.06 for notice (no border) |

The taxonomy drift surfaces three distinct classes of inconsistency:

1. **Missing tier** — timeline silently coalesces `notice` into the default (no-attention) visual, so a `notice`-marked row in a timeline renders identically to a row with no attention at all. DSL authors who declare `notice` expecting a subtle signal see nothing.

2. **Asymmetric encoding** — grid uses border-only, list uses tint-only, queue uses both. The same semantic DSL declaration (`_attention: {level: critical}`) produces visually divergent treatments depending on which region consumes the data. Users scanning a dashboard with both grid and list regions can't build a reliable mental model for what "critical" looks like.

3. **Asymmetric alpha values** — list uses 0.08 (critical, warning) + 0.06 (notice); queue uses 0.04 uniform. Different visual intensity for the same semantic tier.

## Evidence

- **Cycle 275** (UX-066 grid-region contract) — documented 3-tier border-only taxonomy.
- **Cycle 276** (UX-067 timeline-region contract) — documented missing `notice` tier; v2 open question Q1 flagged it.
- **Cycle 277** (UX-068 queue-region contract) — documented unique dual-signal (border + tint).
- **Cycle 278** (UX-069 list-region contract) — documented tint-only with 3-tier alpha variation.
- **Cycle 278 log summary** — explicitly called out the drift as "cross-region alignment candidate".

Additionally, prior implementations that informed this pattern:
- `kanban-board` (UX-040) — does NOT support per-row attention signals (cards are grouped by enum, no individual emphasis). Not an inconsistency; kanban's semantic is different.
- `heatmap-region` (UX-064) — uses a different signal (cell threshold colouring) that's not comparable to per-row attention.

## Root cause hypothesis

The attention signal taxonomy was introduced organically as each region template was written, without a shared helper or macro. Each template's attention-rendering block is a hand-rolled Jinja `{% if attn.level == 'critical' %}...{% elif...` chain:

- `grid.html:15-18` — border only
- `timeline.html:13-15` — bullet colour only (and only 2 tiers)
- `queue.html:54-56` — border + tint
- `list.html:78-80` — tint only

The compiler produces the `_attention` envelope at `src/dazzle_http/runtime/workspace_rendering.py` (grep for `_attention` confirms shared production site), so the source-of-truth for the tier semantics IS canonical. The drift is entirely at the rendering layer.

This is a **Heuristic 4 (defaults-propagation)** class defect: canonical intent declared, canonical resolver correct, but rendering consumers each implemented their own branch logic without a shared macro.

## Fix sketch

**Option A (minimal): shared Jinja macro**
Extract the tier-to-class mapping into a new `macros/attention_accent.html` file:

```jinja
{% macro attention_classes(attn, style='border') %}
  {% if attn %}
    {% set level = attn.level %}
    {% if style == 'border' %}
      border-l-4
      {% if level == 'critical' %}border-l-[hsl(var(--destructive))]{% endif %}
      {% if level == 'warning' %}border-l-[hsl(var(--warning))]{% endif %}
      {% if level == 'notice' %}border-l-[hsl(var(--primary))]{% endif %}
    {% elif style == 'tint' %}
      {% if level == 'critical' %}bg-[hsl(var(--destructive)/0.08)]{% endif %}
      {% if level == 'warning' %}bg-[hsl(var(--warning)/0.08)]{% endif %}
      {% if level == 'notice' %}bg-[hsl(var(--primary)/0.06)]{% endif %}
    {% elif style == 'both' %}
      border-l-4
      {% if level == 'critical' %}border-l-[hsl(var(--destructive))] bg-[hsl(var(--destructive)/0.04)]{% endif %}
      {% if level == 'warning' %}border-l-[hsl(var(--warning))] bg-[hsl(var(--warning)/0.04)]{% endif %}
      {% if level == 'notice' %}border-l-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.04)]{% endif %}
    {% elif style == 'bullet' %}
      {% if level == 'critical' %}text-[hsl(var(--destructive))]{% endif %}
      {% if level == 'warning' %}text-[hsl(var(--warning))]{% endif %}
      {% if level == 'notice' %}text-[hsl(var(--primary))]{% endif %}
      {% if not level %}text-[hsl(var(--primary))]{% endif %}
    {% endif %}
  {% endif %}
{% endmacro %}
```

Each region then imports + uses the macro with its preferred style variant:
- grid: `{{ attention_classes(attn, 'border') }}`
- timeline: `{{ attention_classes(attn, 'bullet') }}`
- queue: `{{ attention_classes(attn, 'both') }}`
- list: `{{ attention_classes(attn, 'tint') }}`

Alpha values kept per-style (list 0.08/0.06, queue 0.04) because visual density differs between regions. The macro pins the *semantic* token mapping; individual style variants keep their visual-intensity choice.

**Option B (consolidation): align tint alphas**
While touching the macro, decide whether all 3 bg-tint variants (list 0.08/0.06, queue 0.04) should use the same alpha. Arguments:
- For alignment: predictable mental model across regions.
- Against: queue has border AND tint (1+1 signals), list has tint alone (1 signal). Alpha of queue's tint can be lower because the border carries half the signal.

**Recommendation**: do Option A first (extract macro). Leave alphas as-is. Revisit Option B in a follow-up cycle after the macro lands and any consumer hasn't regressed.

**Option C (bigger): promote `timeline` to 3-tier**
Fix timeline's missing `notice` tier by updating the template's `{% else %}` branch to explicitly check for `level == 'notice'` before falling through to default:

```jinja
{% if attn and attn.level == 'critical' %}text-[hsl(var(--destructive))]
{% elif attn and attn.level == 'warning' %}text-[hsl(var(--warning))]
{% elif attn and attn.level == 'notice' %}text-[hsl(var(--primary))]
{% else %}text-[hsl(var(--primary))]{% endif %}
```

Note: if default is also `--primary`, the fix is cosmetic (both render the same colour). Currently timeline's default IS `--primary`, so `notice` → default is a no-visible-difference collapse. But promoting `notice` to its own branch makes the taxonomy explicit + allows future divergence (e.g. default → muted grey, notice → primary blue).

## Blast radius

- **Affected regions**: grid (UX-066), timeline (UX-067), queue (UX-068), list (UX-069)
- **Affected apps**: all 5 example apps that use any of these regions — and every downstream Dazzle app that consumes `display: grid|timeline|queue|list` (default mode, so effectively every app).
- **Regression tests needed**: each of the 4 region contracts already has attention-level tests pinning the current behaviour. Changing the behaviour requires updating assertions. Cross-persona: `_attention` envelope is built server-side from access-evaluator results; persona-gated data already drives the envelope correctly.
- **Visual regression risk**: if alphas are aligned in Option B, existing dashboards will see a subtle visual shift. Users may not notice (it's already inconsistent); designers may care.

## Open questions

1. **Is `notice` actually used anywhere?** A grep of the workspace_rendering.py + example DSLs shows `notice` only in test fixtures. In production, `_attention` values flow from entity-specific logic (often based on criticality thresholds). If no real consumer uses `notice`, the "missing tier" finding in timeline is academic.

2. **Should attention tiers be DSL-configurable?** Currently the framework emits `critical | warning | notice`. DSL authors could want domain-specific tiers (`blocked | stalled | late` for a project app). Out of scope for this gap doc; worth a dedicated DSL-design cycle.

3. **Tint alpha normalisation** — should the macro standardise on one value (say 0.06) across all variants? Needs designer input. Currently undocumented but consistent with "queue has 2 signals, list has 1, list's signal is stronger".

4. **Does `kanban-board` (UX-040) benefit from attention signals?** Currently kanban doesn't support them. But a critical-priority ticket in a kanban column could benefit from a left-border accent. Out of scope for the initial macro extraction; could be a v2 kanban enhancement.

5. **Accessibility impact** — attention signal is colour-encoded only. Colour-vision-deficient users lose the signal. A future cycle could add an `aria-describedby` referencing the `attn.message` field, but the macro extraction doesn't need to wait for that.

## Implementation sketch

**Order of operations**:
1. Write `src/dazzle_page/templates/macros/attention_accent.html` with the 4 style variants.
2. Migrate `grid.html:15-18` → `attention_classes(attn, 'border')`.
3. Migrate `timeline.html:13-15` → `attention_classes(attn, 'bullet')`.
4. Migrate `queue.html:54-56` → `attention_classes(attn, 'both')`.
5. Migrate `list.html:78-80` → `attention_classes(attn, 'tint')`.
6. Update each region's regression tests to use the shared mapping (assertions stay the same since the rendered class strings stay identical).
7. Add a new `TestAttentionAccentMacro` class covering all 4 style variants × 3 tiers × presence-of-attn axis.
8. Per Heuristic 3: verify on all 5 example apps before ship — check a representative dashboard still renders attention rows correctly.

**Estimated scope**: one `/ux-cycle` session, ~60-90 min.

**Not in scope**: Option B (alpha normalisation) or Option C (timeline's `notice` tier promotion). Those are follow-up cycles; this gap doc is specifically about the extraction.
