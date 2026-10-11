# Jinja2 Retirement — Postmortem & Hypothesis Evaluation

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-05-12** during the Jinja2 retirement (#1042/#1044). It records the
    migration and the agent-cognition hypothesis behind it; **it may not describe current
    behaviour.** Start from the [documentation home](../index.md), or see
    [Project Evolution](../architecture/evolution.md). The durable decision is [ADR-0023](../adr/0023-template-emission-patterns.md).


**Date:** 2026-05-12
**Versions:** v0.67.79 → v0.67.93 (15 patch releases, one work session)
**Closed:** #1042, #1044, plus #1039, #1040, #1043, #1045, #1046, #1047, #1048, #1049, #1050, #1051

## The hypothesis

> Removing jinja2 leads to a stronger environment for supporting
> agent cognition.

A working framework hypothesis when we started: framework code an
agent needs to read, modify, and reason about is easier to comprehend
when it's all in one language, in one mental model, with consistent
escaping/safety rules and obvious data flow. Jinja2 was a second
substrate — templates, filters, globals, a separate cache, a separate
debugger, a separate set of XSS guarantees. The hypothesis was that
absorbing all rendering into Python would meaningfully improve how
agents work in the codebase.

The retirement is shipped (v0.67.92 dropped the `jinja2` dependency
from `pyproject.toml`; v0.67.93 restored theme support via typed
primitives). Time to evaluate.

## What changed concretely

**Removed:**

| Category | Pre | Post |
|----------|-----|------|
| Jinja templates on disk | 100+ (across v0.67.x sweep) | 0 |
| Production code paths invoking Jinja | 7 distinct sites | 0 |
| Modules importing `jinja2` | 11 | 0 |
| Public API surface for Jinja rendering | `render_fragment`, `render_surface`, `JinjaRenderer`, `override_registry`, `dazzle overrides` CLI | gone |
| Test files containing Jinja env / `render_fragment` | ~65 | 0 |
| LOC in test files (Jinja parity tests) | ~12,000 | 0 |
| Runtime dependency footprint | jinja2 + markupsafe + djlint | markupsafe only |
| Distinct templating syntaxes in the codebase | Jinja2 `{{ }}` / `{% %}`, Python f-strings, stdlib `string.Template` | Python f-strings, stdlib `string.Template` |

**Added:**

| Category | What |
|----------|------|
| Python renderers | `form_renderer`, `detail_renderer`, `table_renderer`, `pdf_viewer_renderer`, `journey_reporter`, `consent_banner`, `provider_html`, `agent_commands.template_strings` |
| Typed primitives carrying chrome config | `Page.font_preconnect`, `AppChrome` dataclass |
| Boot-time resolvers | `resolve_app_chrome` |
| Tests for new modules | `test_app_chrome.py`, `test_page_preconnect.py`, `test_pdf_viewer_*.py`, `test_compliance_wiring.py`, etc. |

**Net diff:** roughly −14,000 / +3,000 lines (heavy delete-favored).

## Evaluating the hypothesis

### Where Jinja-free helps agent cognition

**1. One language, one search index.** Pre-retirement, finding "where
does this badge tone get applied?" required searching `.py` *and*
`.html` (Jinja) files, with different syntax patterns. A `grep
"badge_tone"` returned both Python filter definitions and template
call sites. The agent had to interpret two distinct mental models
(filter vs. function call). Post-retirement: every reference is a
Python call, in a `.py` file, with consistent semantics. This is a
real reduction in cognitive load for ad-hoc spelunking.

**2. Stack traces lead to source you can edit.** Jinja stack traces
land in `_template_renderer.py:482` or — worse — in dynamically
generated template code with no useful line numbers. A typical
"why is this badge rendering wrong?" investigation pre-retirement
involved threading through Jinja's internal compile/render layers.
Post-retirement, the same investigation lands in
`detail_renderer.py:_render_status_badge` directly. Agents already
have a strong "follow the stack trace" instinct; the retirement
makes that instinct produce useful results faster.

**3. Refactors are typed-checkable.** Renaming a Jinja template
field meant updating Python `PageContext` *and* every template that
referenced it, with no compile-time validation. Pre-#1042 we had
many bugs of the form "renamed field on PageContext, forgot to
update template, runtime KeyError on render". Post-retirement,
mypy catches these at lint time. The `Page.font_preconnect`
addition I just shipped was caught by mypy when I missed the kwarg
in `dispatch_render_page` — the same shape of regression
pre-retirement would have shipped to runtime and only surfaced when
a downstream theme tried to use a font preconnect.

**4. Test coverage maps directly to rendering code.** Pre-retirement,
"how is this rendered?" required reading the template *and* the
Python that built its context. Post-retirement, each
`*_renderer.py` is the complete story for what its surface emits.
This is a structural simplification — fewer hops between "the test"
and "the code under test".

**5. No second escaping model.** Jinja's `autoescape=True` /
`| safe` / `Markup(...)` was a parallel security model that agents
had to learn alongside Python's `html.escape`. The retirement
removed that whole class of decision. Every `_renderer.py`
exclusively uses `html.escape` — one rule, applied at the
last-possible moment, easy to audit.

### Where the retirement didn't help (or actively hurt)

**1. Verbose Python.** A 150-line Jinja template (`consent_banner.html`)
became a 130-line Python function (`render_consent_banner`) doing
string concatenation. The Python is more verbose at the line level
— each tag has explicit `<` `>` characters, attributes are escaped
explicitly. For dense markup with little logic, Jinja is genuinely
more compact. Agents reading the new Python version need to track
opening/closing tags across many lines of f-strings.

**2. Lost feature: template overrides as a downstream affordance.**
`override_registry` was a legitimate ergonomic affordance: projects
could author a `templates/foo.html` with `{# dazzle:override
layouts/app_shell.html #}` + `{# dazzle:blocks ... #}` and have the
framework's app chrome cascade through their overrides. Replacing
this with "compose typed primitives directly" raises the floor for
adopters. Theme support is more concrete (it works again as of
v0.67.93) but block-level template override is gone permanently.

**3. Test rewrite burden was real.** ~12,000 lines of parity tests
deleted. Some of those tests caught real bugs in workspace region
rendering (radar geometry, box plot whisker positioning, status-list
chip CSS). The replacement coverage in
`tests/unit/render/fragment/` is leaner but doesn't have the same
shape-specific assertions. We probably regressed in
visual-regression test density. This is fixable (re-author the
tests against the FragmentRenderer output) but it's a real cost
that the hypothesis didn't surface upfront.

**4. The "one language" gain is partly illusory.** We replaced
Jinja with three different stdlib strategies depending on the call
site: `string.Template` (compliance renderer, LLM prompts, vocab
expander), Python f-strings (agent_commands templates), and
hand-rolled HTML string composition (PDF viewer, consent banner,
journey reporter, analytics providers). That's still multiple
mental models — they're just all spelled in Python now. An agent
reading `compliance/renderer.py` after just reading `pdf_viewer_renderer.py`
still has to switch contexts.

### A surprising side effect

**Boot-time cost dropped measurably.** The Jinja env construction
(filter registration, custom globals, loader chain) was load-bearing
on app boot. Post-retirement, `dazzle serve` boots noticeably faster
on cold-start. This wasn't in the hypothesis but is a meaningful
agent-cognition signal in a different sense: the framework feels
faster to iterate against, which compounds across a long agent
session.

## Verdict

The hypothesis is **partially confirmed**. The retirement made the
codebase more legible to agents along the axes the hypothesis
predicted (stack traces, type-checking, single search index, fewer
escaping models). It also incurred costs the hypothesis didn't
surface (verbose Python markup, lost adopter affordances, partial
test-coverage regression).

The biggest cognitive win wasn't the one we expected — it was the
fact that agents can now refactor rendering code under mypy's eye.
Field renames, primitive additions, and chrome-config additions
catch their own mistakes at lint time rather than in production
HTML diffs. This is genuinely transformative for the rate at which
agents can confidently extend the rendering surface.

The biggest cognitive cost wasn't the verbosity — it was the
inconsistency *between* the Python renderers. Each ported subsystem
chose its own substitution model (`string.Template` vs. f-strings
vs. hand-rolled). A future cycle should pick one canonical pattern
for "Python emitting HTML" and converge the renderers on it. That
convergence — not the Jinja deletion itself — is the cognitive
cleanup that would close the gap.

## Recommended follow-ups

1. **Pick a canonical Python-HTML emission pattern** (probably
   f-strings + `html.escape` helpers, matching `pdf_viewer_renderer`
   / `detail_renderer` / `provider_html`). Migrate
   `agent_commands.template_strings` to the same shape so all
   markdown-emitting code looks consistent with all HTML-emitting
   code.

2. **Author visual-regression tests against `FragmentRenderer`**
   output for the workspace regions whose parity tests were
   deleted in v0.67.92 (radar, box plot, bullet, status_list,
   histogram, overlay_series). The Python rendering paths are
   already there — they need pinned shape assertions.

3. **Document the AppChrome contract** as the supported way
   downstream apps configure their chrome. Pre-retirement, projects
   set Jinja env globals directly; now the typed path is
   `AppChrome` + `app.state.fragment_chrome`. An ADR pinning this
   contract closes the migration story.

4. **Restore live theme switching** via a typed island that reads
   `AppChrome.theme_map`. Currently the map is populated but
   unconsumed.

5. **CDN asset routing.** The `AppChrome.use_cdn` flag is
   informational. Wire it through to `dispatch_render_page` so
   `[ui] cdn = true` projects get CDN-hosted bundles again.
