# Patterns Surfaced by `dazzle qa trial`

**Status:** working doc, last updated after the first multi-app sweep
(2026-04-19, five trials across five example apps).

## What the trials saw

Five trials against five Dazzle example apps, each with a unique
business-user persona and a 3-4 task scenario. Aggregate shape:

| App | Persona framing | Steps | Friction items | Verdict |
|-----|----------------|-------|----------------|---------|
| support_tickets | Sarah — SaaS founder | 35 | 2 | Synthesized |
| simple_task | Maya — agency lead | 30 | 7 | Synthesized |
| contact_manager | Tom — accountancy owner | 30 | 3 | Synthesized |
| fieldtest_hub | Priya — eng manager | 35 | 5 | Synthesized |
| ops_dashboard | Dan — SRE | 33 | 11 | **Voluntary** |

## Per-app findings landed as GitHub issues

- **#804** — Alpine.js undefined expressions + HTMX selector failures on list surfaces. Surfaced initially in support_tickets and simple_task; pattern confirms every list surface is affected.
- **#805** — Workspace heading leaks internal `purpose:` string; managers land on "Personal dashboard for support agents."
- **#806** — Empty button labels on workspace pages (likely icon-only without accessible text).
- **#807** — Typed empty states: distinguish empty-collection / no-filter-match / no-permission / loading.
- **#808** — 403 error page should disclose which role was attempting and which roles are permitted.
- **#809** — Demo seed data reads as "UX first_name 2f828c" and undermines qualitative evaluation.

## Seven patterns the trials surfaced

### 1. Alpine.js errors on every list surface

Same console errors on every list view tested across different apps:
`loading`, `colMenuOpen`, `isColumnVisible`, `selected` all undefined.
Filed as #804. Universal. Ships green through the `contracts-gate` job
because nothing in that gate executes JS.

**Lesson:** the static gates don't catch runtime-JS regressions.
Something to watch for: do we need a JS-console-error gate alongside
the contract gate? The trial harness captures it via
`capture_console=True` on the observer — it's essentially free signal
and we should probably surface it as a blocking gate once the known
Alpine issues are cleared.

### 2. Empty-state ambiguity is endemic

Three apps, three flavours of "the screen shows nothing and the user
can't tell why." Filed as #807. The framework has one empty state
template where it needs four (empty / filtered / forbidden / loading).

**Lesson:** the framework's defaults are tuned for happy-path — a
populated list page with filters that match. The *unhappy* paths
(before data exists, when a filter misfires, when access-control
returns zero rows, when the network is slow) all collapse to the
same UX, and real users can tell the difference.

### 3. Demo data quality affects qualitative evaluation

Tom and Maya both flagged placeholder data as "unprofessional" and
used it as a reason to delay adoption. The existing QA fixtures
(`UX first_name 2f828c`) are deliberately artificial for internal
testing but bleed through to any business-user-facing demo. Filed
as #809.

**Lesson:** the signal-to-noise of a qualitative trial depends
heavily on the demo substrate. Making the substrate realistic isn't
cosmetic — it directly changes what the trials can measure.

### 4. 403 without recovery is a dead-end

Dan hit 403 Forbidden on `/app/alert` and `/app/system` despite
pre-auth, with no recovery affordance — just a JSON error body and
a console log. He reported it as a "navigation redirect loop" because
that's how it read to him. Filed as #808.

**Lesson:** error states aren't failure modes — they're *parts of
the product's UX*. The framework knows enough (which role, which
roles permit, which workspace) to turn a 403 into a useful signpost,
but doesn't today.

### 5. Workspaces land users on role-mismatched content

support_tickets' manager lands on "Personal dashboard for support
agents" (#805). ops_dashboard's ops_engineer lands on a workspace
full of empty-state placeholders because their permit rules don't
cover the listed entities. fieldtest_hub's manager hits "No items
found" on their first device list view.

**Lesson:** `default_workspace` gets set based on DSL convention, not
on the *value* that workspace provides to the persona. The first
thing a persona sees should be the most useful view they can access,
not the default dashboard that happens to have been defined.

### 6. Visual design consistently gets praise

Every single trial report includes at least one `praise` observation
about clean layout, at-a-glance dashboards, or clear column choice.
The visual output of Dazzle-generated apps is not the problem.

**Lesson:** investment in raw visual polish has diminishing returns
right now. Investment in the *second-order* experience (empty, error,
first-use, role-mismatch) has high returns because that's where all
the reported friction lives.

### 7. Empty workspaces strand the user

When a workspace opens with zero content AND no prominent create
affordance, the user has nowhere to go. Happened to Maya
(simple_task team_overview with missing assignees), Dan (ops_dashboard
command_center: "No systems registered" with no visible Add button),
and Priya (fieldtest_hub device list).

**Lesson:** empty workspace ≠ nothing to show. The framework could
render first-use scaffolding: *"You haven't added any <entities> yet.
[Add your first <entity>](create)"* when the persona has create
permission. This is a template-level change that would help every
empty-workspace scenario automatically.

## Meta-lessons about the trial loop itself

### LLM step-budgeting is unreliable; fallback verdict is load-bearing

Of five trials, four hit `max_steps` without the LLM calling
`submit_verdict`. Only Dan (the most opinionated persona, with a
more-urgent stop_when framing) voluntarily wrapped up. The fallback
synthesizer is carrying most of the verdict workload — that's fine,
it's cheap, but it means we shouldn't rely on the agent's
self-pacing for anything else.

### Identity framing shapes the signal density

Dan's scenario produced 11 observations; Tom's produced 3. Difference
isn't in the apps — it's in how specifically the persona was
characterised. *"You are skeptical. Toy-looking admin UIs with five
screens to acknowledge an alert will get uninstalled the first time
you're woken up at 3am"* extracts sharper signal than *"You run a
small accountancy practice."* Worth investing in persona voice when
authoring scenarios.

### Dedup works, but is leaky

Trial 1 had the LLM re-file `/dashboard` 404 four times. Post-prompt-
tweak trials still occasionally file near-duplicates (the
simple_task Monday-review praise appears 4× with different wording).
Not worth fighting at the prompt layer — the triager can filter.

### The trial is a qualitative substrate, not a gate

This is a research-grade tool, not a CI check. Run it before a
release, read the output like a field study, and triage into issues.
Don't expect determinism. Don't wire it to CI.

## What to act on next

Priority order based on leverage (roughly: improvement per app × apps
affected):

1. **#804** (Alpine errors) — fix first; affects every list view, currently invisible to CI.
2. **#807** (typed empty states) — framework template change with per-app lift.
3. **#808** (403 with role recovery) — close class of "user is stranded" failures.
4. **#809** (demo data quality) — unlocks better trial signal AND better first-touch demo.
5. **#805**, **#806** — app-specific or more tightly-scoped; lower leverage.

Leave first-use scaffolding (pattern 7) for a future cycle once the
typed-empty-state work in #807 lands — they share template surface.
