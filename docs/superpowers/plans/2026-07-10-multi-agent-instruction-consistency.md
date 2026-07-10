# Multi-Agent Instruction Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip canonical repository policy from `.claude/CLAUDE.md` to `AGENTS.md`, split contributor workflows into `.agents/skills/` (open-standard SKILL.md), generalise loop playbooks to capability language, and gate it all against #1367-style rot.

**Architecture:** Single-source flip with drift-gate repointing (no generation machinery). Four phases, each ships green independently: (1) content flip + gate repoint, (2) skills split + shims, (3) loop generalisation + capability mapping, (4) vendor-name lint + closeout. Spec: `docs/superpowers/specs/2026-07-10-multi-agent-instruction-consistency-design.md`.

**Tech Stack:** Markdown, pytest gates (`pytest.mark.gate`, DB-free), git.

## Global Constraints

- Every phase ends with `/bump patch` + ship discipline (CHANGELOG entry with `### Agent Guidance`, clean worktree, commit in its OWN command, verify HEAD moved, THEN tag+push).
- All new gates carry `pytestmark = pytest.mark.gate` and run DB-free in `pytest tests/unit -m gate`.
- `src/dazzle/services/agent_commands/` and `src/dazzle/core/init_impl/` are OUT OF SCOPE (downstream product templates — follow-up issue only, Task 15).
- Operator loop paths must not move: `.claude/commands/improve.md`, `improve/`, `issues.md`, `fuzz.md`, `xproject.md`, `.claude/skills/phase-contract/` stay where running crons find them.
- Extraction is verbatim: moved prose changes only where a task explicitly says so.
- The eof-fixer pre-commit hook requires trailing newlines; commit messages end with the repo's standard agent attribution trailer.
- `.claude/CLAUDE.md` adapter hard cap: ≤120 lines. `.github/copilot-instructions.md` stub: ≤25 lines.

---

## Phase 1 — The Flip

### Task 1: Content flip + drift-gate repoint (single commit — gates and content must move together)

**Files:**
- Rewrite: `AGENTS.md` (currently a 20-line stub)
- Rewrite: `.claude/CLAUDE.md` (currently ~430 lines)
- Modify: `tests/unit/test_docs_drift.py` (repoint 3 gates, retire 1)

**Interfaces:**
- Produces: `AGENTS.md` carrying the `**Constructs**:` line, `### MCP Tools` table, examples/fixtures list lines, and the `**Version**: X.Y.Z | **Python**: 3.12+ | **Status**: Production Ready` footer — later tasks and `/bump` depend on these exact markers being in `AGENTS.md`.

- [ ] **Step 1: Route sections.** Build `AGENTS.md` by moving these `.claude/CLAUDE.md` sections **verbatim** (current heading line numbers for orientation): Project Overview (5), Architecture (14), Project Layout Convention (36), Style Guide (40), Authoring vs API Boundary (50), Counter-Prior Catalogue (59), Model-Driven Failure Modes (63), Commands (75), DSL Quick Reference (104), Extending (183), Examples (230), LSP Server (238), MCP / CLI Boundary (244), Specification Narrative (321), PyPI Package (345), Architectural Decisions (351), Ship Discipline (370), Onboarding Guides (376), UI Invariants (380), Reports & Charts (387), Test Authoring (402), Gotchas (412), and the version footer line. Open with:

```markdown
# AGENTS.md

Canonical repository instructions for ALL coding agents (any harness). This file is
drift-gated by `tests/unit/test_docs_drift.py` and `tests/unit/test_agent_asset_gates.py`;
its version footer is maintained by the bump workflow. Harness adapters
(`.claude/CLAUDE.md`, `.github/copilot-instructions.md`) must stay thin — project facts
live only here.
```

- [ ] **Step 2: Split the Autonomous Improvement Loop section (140).** The lane table, state-files list, `/fuzz` description, and `improve/capability-map.md` paragraph go to `AGENTS.md` under `## Autonomous Loops (awareness)`, appended with this new paragraph (new content, exact text):

```markdown
Operator loop playbooks live in `.claude/commands/` (they are followable by any capable
harness — see Capability mapping). ANY agent that pushes to `main` must honour the shared
mutation lock `.dazzle/improve.lock` (`PID ISO-timestamp`, 15-min TTL: fresh lock = defer;
stale = remove) and the Ship Discipline section above.
```

The "Common invocations" bullet list (`/improve`, `/improve --status`, `/loop 30m /improve`) moves to the adapter (Step 3).

- [ ] **Step 3: Write the adapter.** Replace `.claude/CLAUDE.md` wholesale with (≤120 lines; Subagent Model Policy (366) and Autonomous Multi-Phase Execution (362) sections move here verbatim):

```markdown
@../AGENTS.md

# CLAUDE.md — Claude Code adapter

Canonical repository policy is `AGENTS.md` (imported above, drift-gated). This file
carries ONLY Claude-Code-runtime specifics; adding project facts here fails
`tests/unit/test_agent_asset_gates.py`.

## Slash-command invocations

- `/improve` — driver picks the lane; `/improve <lane>` forces one; `/improve --status` read-only
- `/loop 30m /improve` — recurring; lane-pickup auto each fire
- `/issues` / `/issues auto` — GitHub issue resolver loop
- `/fuzz` — cross-app boot-stderr sweep
- Contributor workflows (`/ship`, `/check`, `/bump`, …) resolve to `.agents/skills/<name>/SKILL.md`

## Subagent Model Policy

[moved verbatim from current CLAUDE.md lines 366-368]

## Autonomous Multi-Phase Execution

[moved verbatim from current CLAUDE.md lines 362-364]
```

(The bracketed lines are instructions to the implementer, not literal text — paste the two sections verbatim. Until Task 6 lands, the contributor-workflows bullet describes the target state; that is acceptable for one phase.)

- [ ] **Step 4: Repoint gates in `tests/unit/test_docs_drift.py`.**
  - `_claude_md_constructs` → rename `_agents_md_constructs`; path `REPO_ROOT / "AGENTS.md"`; assertion strings `CLAUDE.md` → `AGENTS.md` (lines 26-42, 67-92).
  - `_claude_md_mcp_table` → rename `_agents_md_mcp_table`; same path change (123-139); update `test_claude_md_mcp_tools_table_matches_registry` → `test_agents_md_mcp_tools_table_matches_registry` and its messages (142-190).
  - `test_claude_md_examples_and_fixtures_lists_match_disk` → `test_agents_md_examples_and_fixtures_lists_match_disk`; path change (198-223).
  - **Delete** `test_agents_md_stays_a_stub` (95-120) entirely — superseded; its #1367 rationale moves into the new gate file's module docstring (Task 2).
  - Update the module docstring's `CLAUDE.md` mention to `AGENTS.md`.

- [ ] **Step 5: Run the repointed gates**

Run: `pytest tests/unit/test_docs_drift.py -q`
Expected: PASS (all remaining tests; the stub test is gone).

- [ ] **Step 6: Full gate sweep**

Run: `pytest tests/unit -m gate -q`
Expected: PASS. If `test_gate_marker_complete` or any consumer of the deleted test name fails, fix the reference (grep: `grep -rn "stays_a_stub" tests/ docs/`).

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md .claude/CLAUDE.md tests/unit/test_docs_drift.py
git commit -m "refactor: flip canonical agent instructions to AGENTS.md (spec 2026-07-10)"
```

### Task 2: New gate file + copilot stub

**Files:**
- Create: `tests/unit/test_agent_asset_gates.py`
- Rewrite: `.github/copilot-instructions.md` (currently 120 stale lines)

**Interfaces:**
- Produces: `ADAPTER = REPO_ROOT / ".claude" / "CLAUDE.md"`, `AGENTS = REPO_ROOT / "AGENTS.md"` module constants; Tasks 8 and 13 append gates to this file.

- [ ] **Step 1: Write the copilot stub** (exact content):

```markdown
# Copilot Instructions

Canonical repository instructions live in [`AGENTS.md`](../AGENTS.md) — Copilot reads it
natively; read that file. This stub exists only for surfaces that look for
`.github/copilot-instructions.md` specifically. Do not add project facts here: the
previous full-content version of this file rotted (it referenced modules deleted years
ago) exactly as AGENTS.md once did (#1367). `tests/unit/test_agent_asset_gates.py`
enforces that this file stays a stub.
```

- [ ] **Step 2: Write the failing/passing gate file** (exact content):

```python
"""Structural gates for the multi-harness agent-instruction layout.

AGENTS.md is canonical (see docs/superpowers/specs/
2026-07-10-multi-agent-instruction-consistency-design.md). History: the
pre-#1367 full-content AGENTS.md rotted 21 minor versions behind the
codebase because nothing watched it; the durable fix is single-source +
structural gates. These gates pin the adapters thin so duplicated facts
cannot accrete, and pin the canonical file's version stamp to pyproject.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "AGENTS.md"
ADAPTER = REPO_ROOT / ".claude" / "CLAUDE.md"
COPILOT = REPO_ROOT / ".github" / "copilot-instructions.md"

# Markers whose presence in an adapter means canonical content leaked in.
_CANONICAL_MARKERS = ("**Constructs**:", "### MCP Tools", "Working Dazzle apps in `examples/`:")


def test_claude_md_is_a_thin_adapter() -> None:
    text = ADAPTER.read_text()
    first = next(ln for ln in text.splitlines() if ln.strip())
    assert re.fullmatch(r"@(\.\./)?AGENTS\.md", first.strip()), (
        ".claude/CLAUDE.md must start with the @AGENTS.md import — canonical "
        "policy lives in AGENTS.md."
    )
    lines = len(text.splitlines())
    assert lines <= 120, (
        f".claude/CLAUDE.md is {lines} lines (cap 120). It is a Claude-runtime "
        f"adapter; project facts belong in AGENTS.md."
    )
    for marker in _CANONICAL_MARKERS:
        assert marker not in text, (
            f".claude/CLAUDE.md contains canonical-content marker {marker!r} — "
            f"that content is drift-gated in AGENTS.md and must not be duplicated."
        )


def test_copilot_instructions_is_a_stub() -> None:
    text = COPILOT.read_text()
    assert "AGENTS.md" in text, ".github/copilot-instructions.md must point at AGENTS.md."
    lines = len(text.splitlines())
    assert lines <= 25, (
        f".github/copilot-instructions.md is {lines} lines (cap 25) — it rotted "
        f"once as a full copy; it stays a stub."
    )
    assert not re.search(r"\*\*Version\*\*:", text), (
        "copilot-instructions.md must not carry a version stamp."
    )


def test_agents_md_version_matches_pyproject() -> None:
    agents_match = re.search(r"\*\*Version\*\*: (\d+\.\d+\.\d+)", AGENTS.read_text())
    assert agents_match, "AGENTS.md has lost its version footer (bump target)."
    py_match = re.search(
        r'^version = "(\d+\.\d+\.\d+)"', (REPO_ROOT / "pyproject.toml").read_text(), re.M
    )
    assert py_match
    assert agents_match.group(1) == py_match.group(1), (
        f"AGENTS.md footer says {agents_match.group(1)} but pyproject.toml is "
        f"{py_match.group(1)} — the bump workflow must update both."
    )
```

- [ ] **Step 3: Run the new gates**

Run: `pytest tests/unit/test_agent_asset_gates.py -v`
Expected: PASS (3 tests) — content already flipped in Task 1. If the adapter gate fails on line count, trim the adapter, never the cap.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_agent_asset_gates.py .github/copilot-instructions.md
git commit -m "test: agent-asset structural gates + copilot stub (#1367 class)"
```

### Task 3: Retarget the bump workflow

**Files:**
- Modify: `.claude/commands/bump.md:25-26` and `:43-46`

- [ ] **Step 1: Edit the sed target** (line 25-26): comment becomes `# AGENTS.md — \`**Version**: X.Y.Z\``, command becomes:

```bash
sed -i.bak "s/\\*\\*Version\\*\\*: ${OLD}/**Version**: ${NEW}/" AGENTS.md
```

- [ ] **Step 2: Edit the verification grep** (lines 43-46): the note's "on CLAUDE.md" → "on AGENTS.md"; in the file list replace `.claude/CLAUDE.md` with `AGENTS.md` (pattern unchanged — the footer format moved verbatim).

- [ ] **Step 3: Verify by dry-run**

Run: `OLD=$(grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' pyproject.toml | head -1 | tr -d '"'); grep -c "\*\*Version\*\*: ${OLD}" AGENTS.md .claude/CLAUDE.md 2>/dev/null || true`
Expected: `AGENTS.md:1` and `.claude/CLAUDE.md:0` (footer lives only in AGENTS.md).

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/bump.md
git commit -m "chore: /bump version-stamp target follows the AGENTS.md flip"
```

### Task 4: Adversarial lost-content review

- [ ] **Step 1: Dispatch an independent reviewer subagent** with this rubric: "Diff `git show HEAD~3:.claude/CLAUDE.md` against the union of current `AGENTS.md` + `.claude/CLAUDE.md`, section by section. Report ANY sentence, table row, command, or constraint present pre-flip and absent post-flip. Also verify: every `##` section is accounted for in the spec's routing; no section appears in BOTH files; relative links in moved content still resolve from repo root (`.claude/CLAUDE.md`-relative links like `../docs/...` must become `docs/...` in AGENTS.md — check the hless deep-dive link specifically)."
- [ ] **Step 2: Fix every real finding; re-run** `pytest tests/unit -m gate -q` → PASS.
- [ ] **Step 3: Commit fixes** (if any): `git commit -am "fix: restore content dropped in AGENTS.md flip (review findings)"`

### Task 5: Ship Phase 1

- [ ] **Step 1:** Run `/bump patch`. CHANGELOG entry under Changed + `### Agent Guidance`: "Canonical agent instructions moved from `.claude/CLAUDE.md` to `AGENTS.md` (all harnesses read it natively; Claude Code imports it). `.claude/CLAUDE.md` is now a thin adapter — put project facts in AGENTS.md only."
- [ ] **Step 2:** Run `/ship` (lint, mypy, gate sweep, `mkdocs build --strict`, commit alone → verify HEAD moved → tag → push tag → `fix-deployed` signal).

---

## Phase 2 — Skills Split

### Task 6: Move six contributor command workflows

**Files:**
- Create: `.agents/skills/{ship,check,bump,cimonitor,docs-update,smells}/SKILL.md`
- Rewrite: `.claude/commands/{ship,check,bump,cimonitor,docs-update,smells}.md` as ≤3-line stubs

**Interfaces:**
- Produces: `.agents/skills/<name>/SKILL.md` with YAML frontmatter `name:` and `description:` — Task 8's gate and index depend on the frontmatter shape.

- [ ] **Step 1:** For each of the six, `git mv .claude/commands/<name>.md .agents/skills/<name>/SKILL.md` (create dirs), then prepend frontmatter:

```yaml
---
name: <name>
description: <one line — for ship: "Commit, verify, tag, and push with the repo's pre-flight gate suite">
---
```

- [ ] **Step 2: Generalisation edits on moved content only:**
  - `ship/SKILL.md`: the hardcoded `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` instruction becomes: "End the commit message with your harness's agent-attribution trailer, if it defines one (Claude Code supplies its own; other harnesses use their convention or omit)."
  - `ship/SKILL.md` + `check` + others: leave `/ship`-style cross-references but ensure each names the file path too, e.g. "`/check` (`.agents/skills/check/SKILL.md`)".
- [ ] **Step 3:** Write each stub shim (exact shape, one per command — deterministic choice per spec fallback; symlinks are a later optimisation, recorded as an assumption):

```markdown
Read and follow `.agents/skills/<name>/SKILL.md` (portable home for this workflow).
```

- [ ] **Step 4: Check nothing else referenced the old paths**

Run: `grep -rn "\.claude/commands/\(ship\|check\|bump\|cimonitor\|docs-update\|smells\)" src/ tests/ docs/ .claude/ AGENTS.md | grep -v Binary`
Expected: only this plan/spec and CHANGELOG history. Fix any live reference (AGENTS.md ship-discipline mentions, improve lane playbooks calling `/ship`) to name the new path.

- [ ] **Step 5:** `pytest tests/unit -m gate -q` → PASS. Commit: `git add -A .agents .claude/commands && git commit -m "refactor: contributor command workflows → .agents/skills (open-standard SKILL.md)"`

### Task 7: Move three contributor skills

**Files:**
- Create: `.agents/skills/{dsl-authoring,qa-trial,spec-narrate}/` (git mv whole dirs incl. `qa-trial/references/`, `qa-trial/templates/`)
- Rewrite: `.claude/skills/{dsl-authoring,qa-trial,spec-narrate}/SKILL.md` as shims

- [ ] **Step 1:** `git mv .claude/skills/<name> .agents/skills/<name>` for the three (phase-contract stays).
- [ ] **Step 2:** Recreate `.claude/skills/<name>/SKILL.md` shims — frontmatter must keep the ORIGINAL `name:`/`description:` (Claude Code discovers skills by frontmatter), body is the one pointer line from Task 6 Step 3.
- [ ] **Step 3:** Fix internal relative links in moved skills (`references/authoring-guide.md` links stay valid — they moved together; grep `grep -rn "\.claude/skills/\(dsl-authoring\|qa-trial\|spec-narrate\)" src/ tests/ docs/ AGENTS.md .claude .agents` and repoint live references — `tests/` references to qa-trial templates are the likely hit).
- [ ] **Step 4:** `pytest tests/unit -m gate -q` → PASS; commit: `git commit -am "refactor: contributor skills → .agents/skills; Claude shims keep discovery"`

### Task 8: Workflows index + shim↔skill gate

**Files:**
- Modify: `AGENTS.md` (add `## Workflows` section after Ship Discipline)
- Modify: `tests/unit/test_agent_asset_gates.py` (append gate)

- [ ] **Step 1:** Add to AGENTS.md a `## Workflows` section: intro line "Reusable workflows live in `.agents/skills/<name>/SKILL.md` (open-standard format, any harness):" + one bullet per skill, `- **<name>** — <description from frontmatter>` (9 bullets).
- [ ] **Step 2: Write the failing gate** (append to `test_agent_asset_gates.py`):

```python
def test_agents_skills_have_shims_and_index() -> None:
    """Every .agents/skills/<name> has a Claude shim (commands stub or
    skills stub) and a Workflows-index bullet in AGENTS.md — and no shim
    points at a skill that doesn't exist."""
    skills = {p.name for p in (REPO_ROOT / ".agents" / "skills").iterdir() if p.is_dir()}
    assert skills, ".agents/skills is empty — the split has regressed"
    agents_text = AGENTS.read_text()
    for name in sorted(skills):
        cmd_shim = REPO_ROOT / ".claude" / "commands" / f"{name}.md"
        skill_shim = REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
        shim = cmd_shim if cmd_shim.exists() else skill_shim
        assert shim.exists(), f"no Claude shim for .agents/skills/{name}"
        body = [
            ln for ln in shim.read_text().splitlines() if ln.strip() and not ln.startswith("---")
        ]
        assert any(f".agents/skills/{name}/SKILL.md" in ln for ln in body), (
            f"shim {shim} does not point at .agents/skills/{name}/SKILL.md"
        )
        assert f"**{name}**" in agents_text, (
            f"AGENTS.md Workflows index is missing `{name}`"
        )
```

(Note: the frontmatter filter above lets skill shims keep their YAML block; a commands stub has no frontmatter. If a shim is later made a symlink, `exists()` and the pointer check both still pass via the resolved content — the gate accepts either form.)

- [ ] **Step 3:** Run: `pytest tests/unit/test_agent_asset_gates.py -v` → PASS (4 tests). Deliberately delete one index bullet, re-run → FAIL, restore → PASS (detector-liveness check).
- [ ] **Step 4:** Commit: `git add AGENTS.md tests/unit/test_agent_asset_gates.py && git commit -m "feat: AGENTS.md workflows index + shim↔skill gate"`

### Task 9: Ship Phase 2

- [ ] `/bump patch`; CHANGELOG `### Agent Guidance`: "Contributor workflows (ship/check/bump/cimonitor/docs-update/smells/dsl-authoring/qa-trial/spec-narrate) live in `.agents/skills/<name>/SKILL.md`; Claude slash-commands still work via shims. New workflows go in `.agents/skills/` unless Claude-runtime-specific." Then `/ship`. Verify in THIS session afterwards that `/ship` itself resolved through its shim (it just ran); record the result in the plan-execution notes.

---

## Phase 3 — Loop Generalisation

### Task 10: Capability-mapping table in AGENTS.md

**Files:**
- Modify: `AGENTS.md` (add `## Capability Mapping` immediately after the Workflows section)

- [ ] **Step 1:** Add the section (exact content; this is the ONLY vendor-name zone in AGENTS.md — Task 13's lint depends on this heading text):

```markdown
## Capability Mapping

Playbooks and skills in this repo are written in capability language. This table — the
only place in this file where vendor names may appear — maps each capability to concrete
harness features. Cells marked *degrade* mean: follow the playbook sequentially and note
the degradation in your report.

| Capability | Generic instruction | Claude Code | Codex CLI | Grok Build |
|---|---|---|---|---|
| ask-user-choice | present 2–4 mutually-exclusive options and wait | AskUserQuestion tool | inline prompt | inline prompt |
| task-list | maintain a visible task list for multi-step work | TaskCreate/TaskUpdate | plan mode | plan mode |
| subagent-dispatch | delegate a scoped task to a fresh agent | Agent tool | subtask/spawn if available, else *degrade* | subAgents config |
| parallel-investigation | run independent investigations concurrently | background Agent tool | *degrade* (sequential) | subagents |
| scheduled-loop | re-run a playbook on a cadence | /loop + session cron | external scheduler (CI cron) | headless CI mode |
| web-search | consult current docs when knowledge may be stale | WebSearch tool | built-in browse | built-in search |
| model-tiering | mechanical work → cheapest tier; judgment work → session tier | pins in .claude/CLAUDE.md | single model — n/a | per-subagent model field |
```

- [ ] **Step 2:** Commit: `git add AGENTS.md && git commit -m "feat: capability-mapping table — the vendor-name zone of AGENTS.md"`

### Task 11: Capability-language pass over operator playbooks

**Files:**
- Modify: `.claude/commands/improve.md`, `.claude/commands/improve/lanes/*.md` (6), `.claude/commands/improve/strategies/*.md` (4), `.claude/commands/issues.md`, `.claude/commands/fuzz.md`, `.claude/commands/xproject.md`, `.claude/skills/phase-contract/SKILL.md`
- Modify: `AGENTS.md` (one paragraph), `.claude/CLAUDE.md` (keep pins)

**Interfaces:**
- Consumes: capability names from Task 10 exactly: ask-user-choice, task-list, subagent-dispatch, parallel-investigation, scheduled-loop, web-search, model-tiering.

- [ ] **Step 1: Apply the rename mapping** across the listed files. RENAME ACTUATORS ONLY — control flow, thresholds, lock rules, tier definitions are untouchable:

| Current phrasing | Replacement |
|---|---|
| `AskUserQuestion` (as tool instruction) | "ask the user to choose (ask-user-choice)" |
| "dispatch investigation subagents … `run_in_background: true`" | "dispatch one investigation agent per issue, concurrently where the harness supports it (parallel-investigation, else sequential)" |
| `model: "claude-haiku-4-5-20251001"` pins in playbook prose | "the cheapest-tier model (model-tiering; current pins: `.claude/CLAUDE.md`)" |
| "omit the `model` override so the subagent inherits the session model" | "run judgment work at the session tier (model-tiering)" |
| "the `brainstorming` skill (`superpowers:brainstorming`)" | "a structured brainstorming dialogue (use your harness's brainstorming workflow if it has one)" |
| "Invoke via the Skill tool" | "invoke the named workflow" |

- [ ] **Step 2: Model-policy split.** Append to AGENTS.md Style-adjacent area (immediately after Capability Mapping): "Model policy: mechanical work (lint, fixed-signature scrapes, format churn) runs on the cheapest available tier; judgment work (root-cause, design, review) runs at the session tier. Never pin judgment work below the session tier — pins freeze quality as models advance. Concrete per-harness pins live in the harness adapters." The Subagent Model Policy section in `.claude/CLAUDE.md` keeps the concrete IDs.
- [ ] **Step 3: Semantic-preservation check.** `git diff --word-diff .claude/commands .claude/skills/phase-contract` — review every hunk; any change that isn't in the Step-1 mapping table or a pure phrasing swap is a bug. Numbers (15-min TTL, cap 100, tier tables) must be byte-identical.
- [ ] **Step 4:** `pytest tests/unit -m gate -q` → PASS. Commit: `git commit -am "refactor: operator playbooks speak capability language (semantics unchanged)"`

### Task 12: Ship Phase 3

- [ ] `/bump patch`; CHANGELOG `### Agent Guidance`: "Playbooks now use capability language; resolve capabilities via the AGENTS.md Capability Mapping table. Model pins live only in `.claude/CLAUDE.md`." Then `/ship`.

---

## Phase 4 — Enforcement Sweep + Closeout

### Task 13: Vendor-name lint gate (calibrate FIRST)

**Files:**
- Modify: `tests/unit/test_agent_asset_gates.py` (append)

- [ ] **Step 1: Calibrate against the real corpus** (the #1567 lesson — floor after measuring):

Run: `grep -rInE "\b(Claude|Codex|Copilot|Cursor|Grok|Anthropic|OpenAI|xAI)\b" AGENTS.md .agents/`
Review every hit: (a) inside the `## Capability Mapping` section → fine; (b) generalisable → edit the content now; (c) irreducible (e.g. a PyPI/env-var literal) → allowlist entry with justification comment.

- [ ] **Step 2: Write the gate** (append; adjust `_VENDOR_ALLOWLIST` to exactly the calibrated residual set — an empty tuple is the expected outcome):

```python
_VENDOR_RE = re.compile(r"\b(Claude|Codex|Copilot|Cursor|Grok|Anthropic|OpenAI|xAI)\b")
# Irreducible vendor mentions outside the Capability Mapping zone. Every entry
# needs a justification comment. Expected to stay empty.
_VENDOR_ALLOWLIST: tuple[str, ...] = ()


def _strip_capability_mapping(text: str) -> str:
    if "## Capability Mapping" not in text:
        return text
    head, rest = text.split("## Capability Mapping", 1)
    parts = rest.split("\n## ", 1)
    return head + ("\n## " + parts[1] if len(parts) == 2 else "")


def test_no_vendor_names_outside_capability_mapping() -> None:
    """Portable files must speak capability language (spec 2026-07-10).
    Vendor names are allowed only in AGENTS.md's Capability Mapping section."""
    offenders: list[str] = []
    scan: list[tuple[str, str]] = [("AGENTS.md", _strip_capability_mapping(AGENTS.read_text()))]
    for p in sorted((REPO_ROOT / ".agents" / "skills").rglob("*")):
        if p.is_file() and p.suffix in (".md", ".toml"):
            scan.append((str(p.relative_to(REPO_ROOT)), p.read_text()))
    for label, text in scan:
        for i, line in enumerate(text.splitlines(), 1):
            m = _VENDOR_RE.search(line)
            if m and m.group(0) not in _VENDOR_ALLOWLIST:
                offenders.append(f"{label}:{i}: {line.strip()[:100]}")
    assert not offenders, (
        "Vendor names in portable instruction files (generalise to capability "
        "language, or move to a harness adapter):\n  " + "\n  ".join(offenders)
    )
```

(Note: the AGENTS.md line numbers reported after stripping are approximate — the message includes the line text, which is what the fixer greps for.)

- [ ] **Step 3:** Run `pytest tests/unit/test_agent_asset_gates.py -v` → PASS (5 tests). Liveness check: temporarily add "Claude" to a `.agents` skill body, re-run → FAIL, revert.
- [ ] **Step 4:** Commit: `git add -A tests/unit/test_agent_asset_gates.py AGENTS.md .agents && git commit -m "test: vendor-name lint — portable files speak capability language"`

### Task 14: Validation checklist + cold-read

- [ ] **Step 1:** `mkdocs build --strict` → clean.
- [ ] **Step 2:** `grep -rn "\.claude/CLAUDE\.md" docs/ src/ README.md ROADMAP.md CONTRIBUTING.md | grep -v superpowers` — every live hit must be intentional (adapter references are fine; "canonical instructions" claims must now say AGENTS.md). Fix stragglers.
- [ ] **Step 3: Cold-read validation.** Dispatch a fresh subagent instructed: "You may read AGENTS.md and `.agents/skills/**` but NOTHING under `.claude/`. Task: state (a) how to run the unit-test suite, (b) what gate must pass before shipping, (c) which file to edit to add a DSL construct, (d) the mutation-lock rule for pushing to main." All four answers must be correct from portable files alone; fix AGENTS.md if any fails.
- [ ] **Step 4:** Commit any fixes: `git commit -am "fix: closeout validation findings (cold-read + reference sweep)"`

### Task 15: Follow-up issue + Ship Phase 4

- [ ] **Step 1:** File the deferred-scope issue: `gh issue create --title "Adopt harness-neutral agent-asset layout in generated product templates (dazzle agent-commands / dazzle init)" --body "<summary: downstream projects still get .claude-centric assets from src/dazzle/services/agent_commands/renderer.py + core/init_impl/project.py; adopt the AGENTS.md-canonical + .agents/skills layout proven in-repo by spec 2026-07-10. Include: any vendor-specific features that resisted generalisation (list from Task 13 calibration). Trailer: 🔖 Claude-lens: dazzle>"`
- [ ] **Step 2:** `/bump patch`; CHANGELOG `### Agent Guidance`: "Vendor-name lint is live: portable instruction files use capability language; the Capability Mapping table in AGENTS.md is the only vendor-name zone." Then `/ship`. Confirm clean worktree; done.
