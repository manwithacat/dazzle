# Strategy: job_screen_review

**Lane:** example-apps
**Force path:** `/improve example-apps job_screen_review`
**Panel:** `docs/evaluation/example-job-scenes.toml`

Review an example app as a framework probe. This is a portable procedure:
shell, Dazzle CLI, image inspection, and an agent's own judgement are enough.
Host subagents or workflows can provide independent reviews but are optional.
Do not use the component-catalogue `shadcn_parity` strategy as a visual score.

## 1. Select and freeze one job

Choose one `[[scene]]` from the panel, initially preferring the complex seeded
examples. Read its `trial.toml` scenario and app-local `stems/` before judging
the screen. The panel selects a job; the trial owns its persona narrative and
the DSL/AppSpec owns the app. Run the gate
`pytest tests/unit/test_example_job_scenes.py -q` if any panel or trial entry
changed.

Capture the same persona, workspace, seed, viewport, browser settings, and
theme before and after. `dazzle qa capture --url <running-url> --app <app>
--persona <persona> --workspace <workspace> --above-fold` writes the first
viewport; add `--dark` for the dark scene. Take a full-page diagnostic when
the decision path extends below the fold. Copy the baseline to a local run
directory before the next capture overwrites it. Record the seed revision and
image hashes. Keep runtime secrets and session cookies out of receipts.

## 2. Judge three separate outcomes

1. **Job clarity:** Is the next relevant item visible? Can the persona read its
   state and necessary comparison or context? Is the next action clear? Note
   what useful work is displaced when changing limits or density.
2. **Visual craft:** Use `src/dazzle/core/taste_rubric.py` and
   `docs/reference/taste.md`; cite visible details in light and dark. A
   subjective preference alone does not establish a defect.
3. **Task integrity:** Open a real seeded item and verify the trial's decision
   or action, including values that must agree across queue and detail.
   A still image cannot pass this outcome.

For a before/after comparison, anonymous image pairs and two independent host
agents are preferred when available. A single agent may inspect the pair in
sequence and record a direct, **unblinded** assessment. Do not call that a
blind panel. Save each observation and its limits. Reference parity requires
the eligibility and judge-calibration rules in
`docs/evaluation/agent-first-shadcn-parity.md`; a local pair is not a fleet
score.

## 3. Trace and assign the owner

Run `dazzle inspect page <URL> --project examples/<app>` and, for a specific
region, add `--region <name>`. Use `--html` against the running app when the
response itself is in question. Trace URL → DSL/AppSpec → page context → typed
fragment → HTML. Classify the cause as app DSL, seed, page orchestration,
renderer, Hyperpart, or capture tooling before editing.

Change one coherent cause. App-specific ordering, filters, limits, and copy
belong in the DSL. Shared formatting and conditional chrome belong in the
renderer. Repeatable spacing and component behavior belong in HaTchi-MaXchi.
If the same cause appears in another job or app, test that counterexample
before promoting a framework rule. Preserve access, workflow, and data
semantics; do not add a second maintained HTML or app-spec artifact.

## 4. Verify and record

Validate affected DSL, run focused functional tests and `make ci-changed`,
recapture the exact scene, then repeat the seeded task journey. For an HM
visual change, run the relevant package contracts and visual baseline; if a
baseline is already red, record that limitation instead of claiming green.

Record one concise receipt with scene ID, seed and image hashes, URL and DSL
owner, before/after observation, task result, blind or unblinded preference,
tests, tradeoff, and remaining limitation. Put actionable unresolved findings
in the `example-apps` improve backlog; route shared causes to `framework-ux`
or `hm-convergence`. A wider sweep samples one important job per persona or
app first, then expands around repeated causes rather than counting every
screen equally.

## Toolchain

A live app and a browser where the dig reads a rendered surface. If
`uv run python scripts/improve_toolchain.py --require playwright --require served-app`
exits non-zero, this cycle is `outcome: BLOCKED` with the remedy it prints —
an unrun dig is not a clean dig (#1758 F5).
