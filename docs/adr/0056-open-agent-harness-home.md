# 0056 — Open agent files own the harness

**Status:** Accepted
**Date:** 2026-09-27
**Supersedes in part:** 2026-07-10 multi-agent instruction consistency design
(the decision to leave operator playbooks under `.claude/`)

## Context

`AGENTS.md` already owns repository instructions and `.agents/skills/` owns
contributor workflows. The improve driver, issue loop, fuzz sweep, cross-project
scan, and phase contract still had their authoritative bodies under `.claude/`.
That made the primary operational path depend on one host's discovery layout.
The same tree accumulated host-specific workflow assumptions and stale setup
guidance. Other agents could follow the files manually, but their canonical
location told a different story from the instruction hierarchy.

## Decision

1. `AGENTS.md` remains the single repository instruction entry point.
2. All operator playbooks are canonical `SKILL.md` files under
   `.agents/skills/`. The improve skill owns its lanes, strategies, and
   capability map in that tree.
3. `.claude/CLAUDE.md`, command files, and skill discovery files are pointers
   only. Host settings and hooks remain in their host-specific directory.
4. An operator skill describes the work in capability terms. A host workflow
   may accelerate it, but the skill must include a sequential path when that
   workflow is absent.
5. Canonical skill content is not copied into host adapters. The agent asset
   gate checks pointers, skill metadata, and absence of vendor instructions in
   portable files.
6. Installing Dazzle does not silently register a host-specific MCP server.
   The portable invocation is `dazzle mcp run --working-dir <project>`;
   host-specific setup is explicit.

Existing slash-command names remain entry points for hosts that support them.
Agents that read `AGENTS.md` can invoke the skill by name and follow the same
source. This is a source relocation and instruction cleanup; loop state,
quality gates, and runtime behavior are unchanged.

## Consequences

Live docs, scripts, and workflow prompts point to `.agents/skills/`. Dated
design records retain their historical paths. Host adapters can be removed
later without moving the operational source again. A changed playbook now
passes one shared gate instead of relying on equivalent copies staying fresh.
