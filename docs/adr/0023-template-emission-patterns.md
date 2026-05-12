# ADR-0023: Two-Pattern Template-Emission Model

**Status:** Accepted
**Date:** 2026-05-12
**Supersedes:** N/A
**Related:** #1042 (drop jinja2 umbrella), #1044 (template inventory)

## Context

Post-#1042 the framework no longer ships Jinja2. Every rendering call
site is now pure Python. During the migration each site picked its
own substitution strategy:

- **`string.Template`** — `compliance/renderer.py`, `core/expander.py`,
  `llm_executor.py` (3 sites)
- **F-strings** — `agent_commands/template_strings.py` (1 site)
- **F-strings + a local `_esc()` helper** — `form_renderer`,
  `detail_renderer`, `table_renderer`, `pdf_viewer_renderer`,
  `journey_reporter`, `consent_banner`, `provider_html` (7 sites)

Three patterns is too many. An agent reading two renderers in
succession has to context-switch between substitution models even
though both are pure Python. The convergence question: pick one
pattern, or rationalise why we have more than one.

## Decision

**We keep two patterns, distinguished by *who authors the
template*:**

1. **Pattern A — framework code emits HTML/markdown:** f-strings
   + the canonical `dazzle.render.html.esc(value, *, quote=False)`
   helper.

2. **Pattern B — framework code executes a user-authored template:**
   stdlib `string.Template` with `$var` / `${var}` placeholders.

The choice is mechanical: who writes the template string?

- Dazzle framework engineer writes it → Pattern A.
- Downstream user writes it (in a DSL block, a vocab manifest, a
  project-supplied wrapper HTML file) → Pattern B.

A single shared helper `dazzle.render.html.esc(value, *, quote=False)`
serves Pattern A. Pre-v0.67.94 the same shape was redefined locally
in 7 files; the convergence collapses those to one definition + one
import per file.

## Consequences

### Why not "converge everything on `string.Template`"?

The natural user intuition is "`string.Template` feels more Pythonic
— let's use it everywhere". This is wrong for the dominant case
(framework HTML emission) for three reasons:

1. **`string.Template` is logic-free by construction.** It supports
   `$var` substitution only — no conditionals, no loops, no nested
   structures. The agent_commands `improve.md.j2` Python port has
   `if cmd.signals_consume:`, `if cmd.batch_compatible:`,
   `for kind in cmd.signals_emit:` — real Python control flow over
   ~200 lines of markdown. Converting to `string.Template` would
   split each template into many sub-templates with Python
   orchestration that pre-formats each conditional block as a
   string before substituting. The orchestration is the work; the
   substitution is trivial. F-strings keep both visible together.

2. **F-strings get mypy.** Variable references inside f-strings
   are typed-checkable; `string.Template` placeholders are
   runtime-only. A typo like `$titel` in a template fails on
   `.substitute(...)`, never at lint.

3. **The hand-rolled HTML pattern handles the most complex cases.**
   The PDF viewer's panel iteration, journey reporter's collapsible
   sessions, consent banner's category fieldsets — all have logic
   that wouldn't fit `string.Template`. If the most complex cases
   must be f-strings, forcing the simple ones into a different
   model creates inconsistency for no benefit.

### Why keep `string.Template` at all (Pattern B)?

Three call sites are special — they don't execute templates the
framework wrote; they execute templates a downstream user wrote:

- `core/expander.py` reads the `expansion.body` field of a
  `VocabEntry` defined in the project's `local_vocab/manifest.yml`.
- `llm_executor.py` reads the `prompt_template` field of an
  `LLMIntentSpec` declared in DSL.
- `compliance/renderer.py` reads the project's
  `compliance/templates/document.html` brand wrapper.

For these, the template-author is **a downstream user**, not a
framework engineer. We can't ask them to write Python f-strings —
they don't have a Python file to put them in. `string.Template` gives
them a flat, safe, well-understood substitution format that fits the
authoring surface (a YAML field, a DSL string, an HTML file).

We deliberately gave up Jinja's loops/filters/conditionals in those
three contexts (#1047, #1048, #1050 documented the breaking changes).
That trade-off stands: vocab macros and LLM prompts and PDF brand
wrappers can use flat substitution; if a user needs logic, they
factor it into multiple entries or pre-compose the value in the
calling DSL.

### Why one helper `esc(value, *, quote=False)`, not two
   (`escape` / `escape_attr`)?

The 7 pre-existing local helpers all had the same signature
`_esc(value, *, quote=False)` with ~150 call sites passing
`quote=True` for attribute context. Renaming to two functions would
require rewriting every call site. We tried it during the
convergence and an auto-translation mishandled multi-line
arguments. Keeping the existing signature lets the convergence be a
near-mechanical "delete-local + add-import" edit per file.

A future rename to `escape(value)` / `escape_attr(value)` is a
trivial search-and-replace. We're not committing to the current
signature — we're picking the smallest-blast-radius convergence
move.

## Implementation

- **New:** `src/dazzle/render/html.py` exporting `esc(value, *,
  quote=False)`. Single source of truth.
- **Migrated (v0.67.94):** the 7 HTML emitters delete their local
  `_esc` definition and `import html as _html_mod` line, and add
  `from dazzle.render.html import esc as _esc` in the imports
  block. Every call site stays unchanged.
- **Not migrated:** `compliance/renderer.py`, `core/expander.py`,
  `llm_executor.py`. These remain on `string.Template` per
  Pattern B.
- **Documented:** this ADR. `dazzle/render/html.py` docstring
  references the two-pattern model.

## Agent Guidance

When adding a new renderer, decide:

> **Who writes the template I'm executing?**

- If it's Dazzle framework code (you, an agent, a framework
  engineer): use f-strings. Import `from dazzle.render.html import
  esc as _esc` and escape every interpolated value. Pattern A.

- If it's a downstream user (in a DSL block, a YAML manifest, an
  HTML file under the project's `templates/`): use
  `string.Template(template_str).substitute(**kwargs)`. Pattern B.

Don't mix the two within one renderer. If a Pattern A renderer
needs to interpolate user data, escape that data with `_esc` —
never expose it as a placeholder the user can populate.

## Alternatives Considered

1. **Converge everything on `string.Template`.** Rejected — loses
   conditionals/loops in framework-written templates; forces
   verbose Python orchestration around tiny substitution calls.

2. **Converge everything on f-strings, drop `string.Template` for
   the user-template call sites too.** Rejected — would require
   downstream users to write Python in places that currently take
   text data (DSL prompt strings, vocab manifest YAML, project
   HTML). Removes a legitimate non-Python authoring surface.

3. **Split into `escape(value)` and `escape_attr(value)` (no
   kwarg).** Deferred — the signature improvement is real but the
   migration risk is higher than the benefit. Pick it up as a
   separate ADR if/when the call-site readability matters more
   than the migration cost.

## References

- v0.67.92 / #1042 — `jinja2` dropped from `pyproject.toml`.
- v0.67.93 — theme support restored via typed `AppChrome`.
- v0.67.94 — this convergence shipped (shared `esc` helper).
- `dev_docs/2026-05-12-jinja2-retirement-postmortem.md` — the
  agent-cognition hypothesis evaluation that motivated this ADR.
