# Agent-first path to a shadcn visual parity score

## What the score means

The target is perceived visual quality at the level of a complete job screen,
not React, shadcn class names, component counts, or layout imitation. Record
two outcomes separately:

1. **Craft gap:** blind agent ratings of Dazzle and a valid shadcn reference
   in the same theme and viewport, using the six dimensions in
   `dazzle.core.taste_rubric`. A negative gap means Dazzle trails the reference.
2. **Job clarity:** a same-data browser journey in Dazzle asks whether the
   persona can find the next relevant item, understand its state, and reach
   the correct action. A visual score cannot compensate for failure here.

The public shadcn Tasks example is a useful visual reference for a work queue,
but it has fictional tasks and a table. It is not a substitute for an invoice
settlement journey. For strict same-job comparisons, an agent can implement an
independent reference screen in the shadcn stack from a neutral scene brief;
that reference must be labelled *constructed*, reviewed for data/task fidelity,
and never treated as an official shadcn example.

## Fixed panel and eligibility

Start with the three seeded jobs in `example-job-scenes.toml`: Invoice Ops
finance / Pay Desk, Design Studio reviewer / Review Desk, and HR Records
administrator / Staff Directory. The panel points to each app's `trial.toml`
scenario; it does not duplicate app structure. For
each, capture the first 1440×900 viewport and a full-page diagnostic in light
and dark, with the same seed, persona, app state, and browser settings across
before/after Dazzle revisions. Add empty and error states as separate scenes.
The first public reference candidate is the official shadcn Tasks example,
captured in light and dark on 2026-09-27. It is eligible only for the work-queue
craft comparison. The Design Studio and HR scenes still need eligible analogous
references or constructed same-job screens.

Reject a reference if its HTTP response fails, primary heading or content is
missing, the first viewport is clipped, theme emulation failed, or the image
is blank. Keep URL, capture date, viewport, selector, content check, and image
hash with each accepted reference. The current July mixed pool fails this
eligibility check and cannot be a baseline for the new panel.

## Agent review and score

1. Freeze a scene manifest before edits. Build anonymous image pairs with
   `scripts/agent_taste_pairs.py prepare`; keep source identities in the
   private mapping. Use separate pairs for light and dark.
2. Give at least two independent host agents only the anonymous images and
   the rubric anchors. Require a 1–10 score and one visible observation per
   applicable dimension. For a public example of a different job, ask only
   about craft; do not ask which screen makes the Dazzle task easier.
3. Insert hidden duplicate images to estimate within-panel judge variance.
   If reviewers diverge substantially or cannot cite concrete details,
   recalibrate before publishing a number. Send disagreements, ties, and a
   10% sample of agreements to a human using
   `scripts/agent_taste_pairs.py adjudicate`.
4. For each scene and dimension, report **Dazzle median minus reference
   median**, alongside individual agent ratings and disagreement. Then report
   equal-scene medians and the worst scene. Do not weight by screenshot count
   or mix unrelated role/denial states into one mean.
5. A candidate *parity* claim requires each eligible scene's common-dimension
   gap to lie within a tolerance fixed **before** that run, calibrated from
   duplicate-image judge noise, with no unresolved broken/empty state. Keep
   the job-clarity result beside it. Until enough analogous references and
   calibration exist, publish the gap vector and verdict as **provisional**,
   not a single fleet parity percentage.

## Improvement loop

The reviewer names the most consequential visible detail and its likely
owner: example DSL, page orchestration, renderer, Hyperpart, fixture content,
or capture tooling. The agent traces that detail through URL → DSL/AppSpec →
rendered HTML, makes the smallest coherent change, and recaptures the exact
same scene. It checks browser behaviour and domain task success, then repeats
the blind comparison. One accepted improvement is one paired scene delta plus
a correct journey, not a higher pooled score caused by changing the sample.

## First pilot

`shadcn-pilot-cases.json` pairs the seeded Invoice Ops Pay Desk with the freshly
captured shadcn Tasks light screenshot. It is **craft-only** because the jobs and
data differ. It tests the anonymous review flow; it cannot yield a fleet parity
score. `scripts/agent_taste_pairs.py prepare` produced an anonymous pack at
`.dazzle/qa/agent-first/shadcn-pilot/blind/`; the mapping is outside that pack.
The reference PNG is gitignored. To reproduce the pack after cloning, capture
the reference and the seeded Pay Desk screenshot first, then run:

```bash
.venv/bin/python scripts/taste/capture_references.py --only shadcn_tasks
.venv/bin/python scripts/agent_taste_pairs.py prepare \
  docs/evaluation/shadcn-pilot-cases.json \
  .dazzle/qa/agent-first/shadcn-pilot/blind \
  .dazzle/qa/agent-first/shadcn-pilot/private-map.json --seed 27
```

Use an empty destination directory for each run; the pack tool refuses to
overwrite an existing blind pack.

Two independent agents reviewed the pack without source identities. Both
preferred B for craft; unblinding identified A as Dazzle and B as shadcn.
The table gives the median score from the two agents on the 1–10 rubric:

| Dimension | Dazzle | shadcn | Dazzle minus reference |
|---|---:|---:|---:|
| Typographic hierarchy | 6 | 8 | −2 |
| Spatial rhythm | 5 | 8 | −3 |
| Color discipline | 5.5 | 8 | −2.5 |
| State completeness | 6 | 8 | −2 |
| Perceived craft | 5.5 | 8.5 | −3 |

Both independently cited excess vertical space before the first Past Due row,
uneven seven-tile metrics, and competing pastel fills. This is a **directional
single-scene result**, not a shadcn parity score: there is no hidden duplicate
for noise calibration, no human agreement check, no dark Dazzle pair, and no
same-job reference. The agents differed by two points on Dazzle state
completeness, so that dimension particularly needs calibration.
The raw Dazzle/shadcn scores in rubric order (typography, rhythm, color,
state, craft) were reviewer 1: `6/8, 5/8, 6/8, 7/8, 6/9`; reviewer 2:
`6/8, 5/8, 5/8, 5/8, 5/8`.

The first improvement candidate is the Pay Desk metrics/queue composition.
Trace: `settle_metrics` and `past_due` in `examples/invoice_ops/dsl/payments.dsl`
→ metric and queue fragments in `src/dazzle/render/fragment/renderer/_render_tables.py`
→ `packages/hatchi-maxchi/components/metrics.css` and `queue.css`. Test whether
a smaller set of settlement-relevant metrics and tighter queue chrome improves
the same seeded screenshot **without** hiding disputed or approval work. A
correct invoice settlement journey remains a separate acceptance condition.

### Iteration 1 — focus the settlement band

The Pay Desk now shows Ready, On Time, Past Due, and Disputed in one metric row.
Draft, approval, and conversation counts left the top band; their queues and
discussion remain on the desk. The four tiles use one accent, one danger tone,
and neutral fills for the other two. In the seeded 1440×900 recapture, the
first past-due invoice starts roughly 70 pixels higher than before. The dark
recapture retains readable contrast.

Two independent agents then reviewed an anonymous same-data before/after pair.
Both chose the new screen for job clarity and craft: the oldest overdue invoice
is reached after one aligned metrics row, with less competing color. Both also
noted that the screenshot alone cannot prove the invoice click reaches the
settlement decision. That browser journey and the separate shadcn craft gap
are the next checks; this paired preference is an improvement signal, not a
new parity score.

### Iteration 2 — verify the payment decision

An authenticated browser journey from the Past Due queue reached invoice
`NW-2026-038` and exposed its payment and dispute actions. The journey also
found an amount defect: the queue showed `6750.00`, while the detail summary
showed `£67.50`. The seeded invoice and its two line items total `6750.00` GBP
in major units. The detail renderer had lost the surface's explicit
`format: currency:GBP` and inferred the minor-unit money path from the field
name.

The view-field compiler now carries that format through the detail context to
the same typed cell formatter used by lists. The seeded detail response shows
`£6,750.00`; targeted tests cover the major-unit override while retaining the
minor-unit money case, and `make ci-changed` passed. This is a task-integrity
gate for financial pages. Visual preference alone would have missed it.

The next recapture exposed a mixed-currency case: `NW-2026-039` is EUR, so a
hard-coded GBP surface format was also wrong. Invoice list and detail now use
`format: currency` with the record's currency field. Invoice queue projections
include that field, allowing the existing amount/currency folding rule to show
`GBP 6,750.00` and `EUR 15,400.00` without an extra currency chip. Focused
tests check GBP and EUR in detail, list rows, and CSV; the live seeded detail
responses and `make ci-changed` passed. Line-item unit amounts remain a separate
model question because LineItem has no currency field of its own.

The currency change risks model/runtime divergence if the row's `currency`
field is absent or means something else. Its detector is live in the normal
changed-file gate: paired detail, grid, and CSV tests plus the seeded browser
journey. The trace remains `field amount format: currency` in DSL → AppSpec
field format → row currency → typed cell formatter; stored decimal values,
access rules, and payment transitions stay in their existing model.

The next visual candidate is the invoice detail heading and decision strip.
At 1440×900, four equal-weight actions wrap onto two lines and the four-field
status strip repeats Due Date and Dispute Reason already shown nearby. The Pay
Desk also promotes `New Invoice Document` as its heading action even though
settlement is the finance persona's current job. Check action provenance and
task completion before changing the chrome or DSL projection.

### Iteration 3 — keep contextual creation at the record

The heading action came from automatic workspace create-action inference: a
later InvoiceDocument region had a CREATE surface and finance permission, so
it became the Pay Desk's most prominent button. The inference now treats an
entity with a required reference to another source on the same workspace as
contextual. InvoiceDocument creation remains available where documents are
the main source; tenant references do not trigger this suppression. The
authenticated Pay Desk recapture has no `New Invoice Document` heading action,
and the overdue invoice still opens a detail page with `Set to Paid` and the
correct amount. Unit tests and `make ci-changed` passed; the dark recapture
remains readable.

Two independent agents reviewed an anonymous same-data before/after pair.
Both chose the version without the unrelated heading button for job support
and, narrowly, visual craft. They cited the button's saturated blue emphasis
competing with the overdue queue; they also found the rest of the layout
virtually unchanged. Both still noted a large blank band above the first
overdue row and no direct settlement action in the screenshot. The paired
preference supports this correction; it is not a new shadcn parity score.

This runtime inference risks hiding a genuinely primary create action when an
entity has a required relationship to another visible source. The live
detector is the workspace-action unit test covering contextual, standalone,
and tenant cases plus the seeded browser journey. The trace is workspace
region sources + entity required references in AppSpec → inferred heading
actions → per-persona create gate; database, auth, and workflow semantics are
unchanged.

### Iteration 4 — bring work rows closer to the heading

The Past Due queue rendered a separate count row even when all three invoices
were visible, then gave every row 16px of vertical padding below a dashboard
body's 24px top padding. The renderer now emits a queue count only when the
total exceeds the visible rows; capped queues still show their count and
“Showing N of M” line. The HM queue row keeps 16px horizontal padding but uses
8px vertically. The dashboard-card host uses 8px top padding for queue bodies.
The seeded first invoice starts about 48px higher; the dark recapture remains
legible. Queue and related-queue tests cover the count condition, 357 focused
render/contract tests, 81 HM contract/blueprint tests, and `make ci-changed`
passed. The CSS change also regenerated the HM bundles and UX catalogue.

Two independent blind reviewers chose the revised same-data screen for finding
overdue work and, modestly, for visual craft. They cited the tighter relation
between heading and rows. One noted the local count badge disappeared, although
the Past Due metric still says 3; the other noted that the dashboard card's
minimum height leaves empty space below the third row. This paired result is
directional and does not change the provisional shadcn gap vector.

The HM local visual-baseline test fails for queue and card screenshots even
with the CSS source restored to its pre-iteration state. It therefore cannot
be used as a clean regression signal for this edit in the current checkout;
the baseline needs its own reconciliation before a visual ship. The normal
changed-file gate and package contract tests are green. The remaining card
space is a CLS reservation, so the next change must measure loading shifts as
well as the settled screenshot before reducing it.

### Iteration 5 — compare creative review states on the first screen

The seeded Design Studio Review Desk showed four in-review assets in a
three-column grid. The fourth wrapped onto a mostly empty second row, pushing
the approved creative wall entirely below the 1440×900 viewport. The DSL now
caps each preview wall at three assets. In the paired recapture, the reviewer
can see the three in-review previews and the approved section with three
previews in the same first screen. The dark capture retains readable preview
labels. The unrelated `New Design Feedback` heading action is also absent
because of iteration 3's contextual-create rule; that was held constant in
the fresh before/after pair.

Two independent blind reviewers preferred the revised same-data screenshot
for seeing both states. Both also preferred its craft, one only slightly:
the one-row walls look balanced, while the old wall had a sparse second row.
One reviewer reported a partial viewport crop in their own inspection, so
the direct saved screenshot remains the stronger evidence of which content
is visible. The cap means one in-review asset leaves the top preview wall;
the asset catalog still exposes it. A screenshot
cannot prove the asset-detail interaction or accessibility, and Design Studio
has no eligible external reference yet. This is a paired local improvement,
not a parity score.

`dazzle validate`, all 15 focused Design Studio media tests, and
`make ci-changed` passed. The trace is `review_pixels` and `approved_pixels`
limits in the workspace DSL → AppSpec regions → grid fragments; no new
runtime abstraction or database semantics were introduced. The stem now
records the one-row review comparison as the reviewer default.
