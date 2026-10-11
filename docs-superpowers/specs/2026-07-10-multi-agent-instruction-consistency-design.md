# Multi-Agent Instruction Consistency — Design

**Date**: 2026-07-10
**Status**: Approved for planning
**Drivers**: New collaborators using OpenAI Codex, OpenAI chat-based tools, and xAI Grok
Build need consistent repository instructions regardless of harness. Industry state has
changed since #1367: AGENTS.md is now a Linux Foundation (AAIF) standard read natively by
Codex, Cursor, Copilot, Gemini CLI, Windsurf, Zed, and Grok Build (root-down merge,
Codex-style); the Agent Skills SKILL.md format is a cross-tool open standard; Grok Build
additionally auto-reads `CLAUDE.md` and `.claude/` (skills, MCPs, hooks) with zero config.
Claude Code's native file remains `CLAUDE.md`, with `@AGENTS.md` import as the documented
bridge.

## Prior art (why this design looks the way it does)

- **#1367**: a full-content AGENTS.md rotted 21 minor versions behind and misled agents →
  replaced with a drift-gated pointer stub. Lesson: duplicated instruction content without
  enforcement rots. The fix is single-source + gates, and at the time there were zero
  non-Claude consumers, so the single source stayed at `.claude/CLAUDE.md`.
- **v0.92.88**: `.agents/skills` deleted because nothing read it and it duplicated
  `.claude/skills`. Lesson: a "neutral" location with no consumer is pure liability.
- **Now**: there ARE consumers (Codex/Grok/OpenAI collaborators), and the standards they
  read natively exist. The consumer-side premise of both reversions has inverted; the
  rot-prevention discipline (drift gates) carries over unchanged.

## Decisions (locked with user, 2026-07-10)

1. **Scope: full parity ambition.** Everything feasible becomes harness-neutral, including
   the improvement-loop playbooks; Claude-runtime features degrade gracefully elsewhere.
2. **Canonical source: flip to AGENTS.md.** Portable policy lives in AGENTS.md; drift
   gates and `/bump` repoint to it; `.claude/CLAUDE.md` becomes a thin adapter.
3. **Skills home: split by audience.** Contributor workflows → `.agents/skills/` (SKILL.md
   open-standard format). Operator loops (improve/issues/fuzz/xproject/phase-contract)
   stay in `.claude/`.
4. **Product templates deferred.** `dazzle agent-commands` / `dazzle init` generated
   assets for downstream projects are a follow-up issue, filed at closeout — prove the
   model in-repo first (same sequencing as HM).

## Target layout

```
AGENTS.md                          # CANONICAL repository policy (drift-gated, version-stamped)
.agents/skills/<name>/SKILL.md     # contributor workflows, open-standard format
  ship/  check/  bump/  cimonitor/  docs-update/  smells/
  dsl-authoring/  qa-trial/  spec-narrate/
.claude/CLAUDE.md                  # adapter: line 1 = @AGENTS.md, + Claude-runtime section, ≤120 lines
.claude/commands/<name>.md         # shims → .agents/skills/<name>/SKILL.md (contributor workflows)
.claude/commands/improve.md        # operator loops: physical + logical home unchanged
.claude/commands/improve/          #   (lanes/, strategies/)
.claude/commands/issues.md  fuzz.md  xproject.md
.claude/skills/phase-contract/     # operator skill, stays
.claude/settings.json, hooks/      # vendor-specific configuration, stays (per task-doc rule)
.github/copilot-instructions.md    # ≤25-line pointer stub (Copilot reads AGENTS.md natively)
```

No `.codex/` directory: Codex reads AGENTS.md natively; adding one would be duplication.

## Content split (the flip)

**AGENTS.md** receives the portable sections of today's `.claude/CLAUDE.md`, extracted
**verbatim** (prefer extraction over rewriting; no wording churn beyond what the
vendor-name lint requires): project overview, architecture table, project layout
convention, style guide, authoring-vs-API boundary, counter-prior catalogue, model-driven
failure modes rule, commands (dev setup / validate / test / lint), DSL quick reference +
scope rules + hless note, MCP/CLI boundary + the drift-gated MCP tool table, CLI command
list, spec-narrative section, examples + fixtures lists (drift-gated), extending, API
surface snapshots, LSP, PyPI package, ADR constraints, ship discipline, onboarding
guides, UI invariants, reports & charts, test authoring, gotchas — and the **version
stamp footer** (`**Version**: X.Y.Z | …`), which `/bump` retargets to.

New AGENTS.md-only sections:

- **Capability mapping** (see below) — the only section where vendor names are permitted.
- **Workflows index** — one line per `.agents/skills/*` entry (name + description) so
  harnesses that don't scan directories discover them.
- **Autonomous loops (awareness)** — the lane table and state-file list from today's
  "Autonomous Improvement Loop" section (harness-neutral facts), plus: operator loop
  playbooks live in `.claude/commands/`; ANY agent pushing to main must honour the shared
  mutation lock `.dazzle/improve.lock` (15-min TTL) and the ship discipline. Slash-command
  invocation idioms (`/improve`, `/loop 30m /improve`) go to the adapter; playbook detail
  stays in the playbooks.

**`.claude/CLAUDE.md` adapter** (≤120 lines, gate-enforced): line 1 is `@AGENTS.md`;
then only Claude-runtime content — subagent model policy with concrete pinned model IDs,
`/improve`–`/loop`–`/issues` invocation idioms, phase-contract skill pointer, Claude-side
memory notes. It must contain none of the drift-gated table markers (`**Constructs**:`,
the MCP tool table header, examples/fixtures list lines).

**`.github/copilot-instructions.md`**: replaced by a ≤25-line stub pointing at AGENTS.md.
The current 120-line version is confirmed stale (names `src/dazzle/stacks/` and
`core/ir.py`, both long gone) — it is the #1367 failure mode reproduced and must not
survive in full-content form.

## Capability mapping (the full-parity mechanism)

One table in AGENTS.md; playbooks and skills reference capabilities, never tools:

| Capability | Generic instruction | Claude Code | Codex CLI | Grok Build |
|---|---|---|---|---|
| ask-user-choice | present 2–4 mutually-exclusive options, wait | AskUserQuestion | inline prompt | inline prompt |
| task-list | maintain a visible task list for multi-step work | TaskCreate/TaskUpdate | plan mode | plan mode |
| subagent-dispatch | delegate a scoped investigation/implementation to a fresh agent | Agent tool | (spawn/subtask equivalent) | subAgents config |
| parallel-investigation | run independent investigations concurrently | background Agents | sequential fallback | subagents |
| scheduled-loop | re-run a playbook on a cadence | /loop + cron | external scheduler (CI cron) | headless CI mode |
| web-search | consult current docs when knowledge may be stale | WebSearch | built-in browse | built-in search |

(Exact per-harness cells verified at implementation time; unknown cells say "sequential
fallback" or "not available — degrade as noted in the playbook".) Model selection policy
generalises in AGENTS.md to the principle — *mechanical work → cheapest tier; judgment
work → session-tier model; never hardcode a mid-tier* — with concrete model IDs only in
the CLAUDE.md adapter.

Loop playbooks (`improve.md`, lanes, strategies, `issues.md`, `fuzz.md`) get a
capability-language pass: "AskUserQuestion" → ask-user-choice phrasing, Agent-tool
dispatch idioms → subagent-dispatch phrasing, `model: "claude-haiku-…"` pins → "cheapest
tier (see adapter for the current pin)". Semantics unchanged — this is renaming the
actuators, not the logic. They remain physically in `.claude/commands/` (operator home)
but become followable by any capable harness; Grok reads them in place today.

## Skills split

| Asset | Audience | Action |
|---|---|---|
| commands: ship, check, bump, cimonitor, docs-update, smells | contributor | → `.agents/skills/<name>/SKILL.md`, generalisation pass |
| skills: dsl-authoring, qa-trial, spec-narrate | contributor | → `.agents/skills/<name>/` (keep references/ substructure) |
| commands: improve (+ improve/), issues, fuzz, xproject | operator | stay `.claude/commands/`, capability-language pass |
| skills: phase-contract | operator | stays `.claude/skills/`, capability-language pass |
| settings.json / settings.local.json / hooks/ | vendor config | keep as-is (no portable abstraction exists) |

Moved skills get normalized SKILL.md frontmatter (`name`, `description`) per the open
standard. Known generalisation fix: the ship skill's hardcoded
`Co-Authored-By: Claude Opus 4.8 …` line becomes "append your harness's agent-attribution
trailer" (the concrete trailer for Claude Code arrives via its system prompt / adapter).

**Claude Code discovery shims**: `.claude/commands/<name>.md` for each moved contributor
workflow. Try symlinks to `../../.agents/skills/<name>/SKILL.md` first; if Claude Code
does not resolve symlinked command files (verify at implementation), fall back to
one-line stub files ("Read and follow `.agents/skills/<name>/SKILL.md`."). A gate
enforces the 1:1 shim↔skill correspondence either way.

## Enforcement gates (all `pytest.mark.gate`, DB-free)

Existing, repointed in `tests/unit/test_docs_drift.py`:
1. Constructs line ↔ parser dispatch — path changes to `AGENTS.md`.
2. MCP tool table ↔ `get_all_consolidated_tools()` — path changes to `AGENTS.md`.
3. Examples/fixtures lists ↔ directory trees — path changes to `AGENTS.md`.
4. The old "AGENTS.md must remain a stub" test is **retired** (superseded, not violated —
   its docstring's rationale is preserved by the new gate family below).

New, in `tests/unit/test_agent_asset_gates.py`:
5. **Thin-adapter gate**: `.claude/CLAUDE.md` first content line is `@AGENTS.md`; ≤120
   lines; contains no drift-gated table markers.
6. **Copilot stub gate**: `.github/copilot-instructions.md` ≤25 lines, references
   AGENTS.md, no version stamp.
7. **Vendor-name lint**: `\b(Claude|Codex|Copilot|Cursor|Grok|Anthropic|OpenAI|xAI)\b`
   forbidden in AGENTS.md outside the "Capability mapping" section, and in
   `.agents/skills/**` entirely. Small explicit allowlist constant for unavoidable cases
   (e.g. `ANTHROPIC_PRICING_PER_MTOK` if it appears in moved content); every allowlist
   entry carries a justification comment.
8. **Shim↔skill gate**: every `.agents/skills/<name>/` has a `.claude/commands/<name>.md`
   shim and vice versa; shims are symlinks or ≤3-line stubs.
9. **Version-stamp gate**: AGENTS.md footer version == `pyproject.toml` version (replaces
   the CLAUDE.md leg of the /bump verification).

Tooling repoints in the same commit as the flip: `/bump`'s sed target for the
`**Version**:` line (`.claude/CLAUDE.md` → `AGENTS.md`; still six canonical locations,
one changes identity), and the bump skill's own verification grep.

## Migration phases (each ships green independently, `/bump patch` each)

1. **Flip** — AGENTS.md extraction; CLAUDE.md adapter rewrite; retire stub gate; repoint
   content gates; add gates 5/6/9; /bump retarget; copilot stub. *Adversarial review
   before ship* (this phase can silently drop guidance — reviewer diffs section-by-section
   against the pre-flip CLAUDE.md for lost content).
2. **Skills split** — move nine contributor workflows; shims (symlink-or-stub decision
   made here); workflows index in AGENTS.md; generalisation pass on moved content; gate 8.
3. **Loop generalisation** — capability mapping table in AGENTS.md; capability-language
   pass over improve/lanes/strategies/issues/fuzz/phase-contract; model-policy split
   (principle → AGENTS.md, pins → adapter).
4. **Enforcement sweep + closeout** — gate 7 (vendor-name lint) last, after all content
   has moved (calibrate the allowlist against the real corpus before flooring — the
   #1567 lesson); validate against the original task doc's checklist (no guidance lost,
   no semantics changed, references valid, no duplicated policy, vendor files minimal);
   file the follow-up issue for `dazzle agent-commands` / `dazzle init` product templates.

## Risks & mitigations

- **Guidance silently dropped in the flip** → phase-1 adversarial review with explicit
  section-by-section diff; the task doc's validation checklist is the review rubric.
- **Claude Code symlink discovery unknown** → verify at implementation; stub fallback
  designed in; gate 8 accepts either form.
- **Running crons /improve /issues** → operator loop paths unchanged; contributor shims
  keep `/ship`, `/bump` invocations working mid-migration.
- **Memory files referencing `.claude/CLAUDE.md`** → file continues to exist as adapter;
  no memory rewrites needed.
- **`dazzle agent-commands` writing AGENTS.md** → it writes into *downstream* project
  roots, not this repo; noted in the follow-up issue so the product templates adopt the
  same layout later.
- **Vendor-lint false positives** (e.g. Co-Authored-By trailers, model-ID mentions in
  moved content) → generalise the content where possible; explicit justified allowlist
  where not; lint lands last (phase 4) after calibration.

## Validation (task-doc checklist, run at closeout)

- No guidance accidentally removed (phase-1 review artifact).
- No workflow semantics changed (capability-language pass is rename-only).
- All references valid (`mkdocs build --strict`; gate suite; grep for dangling
  `.claude/commands/<moved>` references in docs/ and src/).
- No duplicated policy remains (adapter + stub gates enforce structurally).
- Every skill has a clear purpose (frontmatter descriptions reviewed in phase 2).
- Vendor-specific files minimal (gates 5–7).
- Cold-read check: a fresh non-Claude agent (or a simulated run given only AGENTS.md +
  `.agents/skills/`) completes a small representative task without needing `.claude/`.

## Deliverables

1. New directory structure per Target layout.
2. Migrated files (verbatim-extracted policy; generalised workflows).
3. Migration report — the phase-1 review artifact + per-phase CHANGELOG entries with an
   **Agent Guidance** section announcing the new canonical file to agents.
4. Assumptions log (symlink support, per-harness capability cells) recorded in this spec's
   companion plan as they are resolved.
5. Follow-up issue: product templates (deferred by decision 4); plus any vendor-specific
   features that resist generalisation, listed in the closeout issue comment.
